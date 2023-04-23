#!/usr/bin/env python3
#
# -----------------------------------------------------------------------------
# Copyright (c) 2022 Martin Schobert, Pentagrid AG
#
# All rights reserved.
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
#  ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
#  WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
#  DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
#  ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
#  (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
#  LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
#  ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#  (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
#  SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
#  The views and conclusions contained in the software and documentation are those
#  of the authors and should not be interpreted as representing official policies,
#  either expressed or implied, of the project.
#
#  NON-MILITARY-USAGE CLAUSE
#  Redistribution and use in source and binary form for military use and
#  military research is not permitted. Infringement of these clauses may
#  result in publishing the source code of the utilizing applications and
#  libraries to the public. As this software is developed, tested and
#  reviewed by *international* volunteers, this clause shall not be refused
#  due to the matter of *national* security concerns.
# -----------------------------------------------------------------------------


import configparser
import logging
import os
import queue
import sys
import threading
import time
import traceback

import helper
import modem
import modemconfig
import modempool
import rpcserver
import smtp


class SmsGate:
    """
    Class representing the SMS Gateway
    """

    def __init__(self, config: configparser.ConfigParser) -> None:
        """
        Create a new SMS Gateway object.
        @param config: A ConfigParser object.
        """

        self.config = config
        self.smtp_delivery_queue = queue.Queue()
        self.event_available = threading.Event()

        self.l = logging.getLogger("SmsGate")

        # initialize sub-modules
        self._init_smtp_delivery()
        self._init_pool()
        self._init_rpcserver()

    @staticmethod
    def read_sim_config(conf_file: str = "conf/sim-cards.conf") -> configparser.ConfigParser:
        """
        Read SIM card configuration from an INI file.
        @param conf_file: The name of the INI file.
        @return: Returns a ConfigParser object.
        """
        config = configparser.ConfigParser()
        config.read(conf_file)
        return config

    @staticmethod
    def read_config(conf_file: str = "conf/smsgate.conf") -> configparser.ConfigParser:
        """
        Read SMS Gateway configuration from an INI file.
        @param conf_file: The name of the INI file.
        @return: Returns a ConfigParser object.
        """
        config = configparser.ConfigParser()
        config.read(conf_file)
        return config

    def _init_rpcserver(self) -> None:
        """
        Initializes the XMLRPC server module.
        """
        self.l.info("Init RPC server")

        self.server_thread = threading.Thread(
            target=rpcserver.set_up_server,
            args=(self.config, self.pool, self.smtp_delivery),
        )
        self.server_thread.start()

    def _init_smtp_delivery(self) -> None:
        """
        Initializes the SMTP module
        """
        if not self.config.getboolean("mail", "enabled", fallback=True):
            return

        self.smtp_delivery = smtp.SMTPDelivery(
            self.config.get("mail", "server"),
            self.config.getint("mail", "port", fallback=465),
            self.config.get("mail", "user"),
            self.config.get("mail", "password"),
            self.config.getint("mail", "health_check_interval", fallback=600),
        )

        self.smtp_delivery_thread = threading.Thread(target=self._do_smtp_delivery)
        self.smtp_delivery_thread.start()

    def _do_smtp_delivery(self):
        """
        Internal method that checks the delivery queue for outgoing SMS that should be sent via SMTP.
        """

        while True:
            try:
                self.l.debug("Check delivery queue if E-mail should be sent.")
                _sms = self.smtp_delivery_queue.get(timeout=10)
                self.l.info(f"[{_sms.get_id()}] Event in SMS-to-Mail delivery queue.")
                if _sms:
                    self.l.info(f"[{_sms.get_id()}] Try to deliver SMS via E-mail.")

                    # Check if the modem config has a specific recipient
                    recipient = _sms.get_receiving_modem().get_modem_config().email_address
                    if recipient is None:
                        self.l.debug("Failed to look up recipient's e-mail address in modem config.")
                        # Otherwise read recipient from main configuration
                        recipient = self.config.get("mail", "recipient")

                    self.l.debug(f"Will send e-mail to {recipient}.")

                    if self.smtp_delivery.send_mail(recipient, _sms):
                        self.l.info(f"[{_sms.get_id()}] E-mail was accepted by SMTP server.")
                    else:
                        self.l.info(f"[{_sms.get_id()}] There was an error delivering the SMS. Put SMS back into "
                                    "queue and wait.")
                        self.smtp_delivery_queue.put(_sms)

                        # Update health data: The loop "prefers" delivering mails and deferrs the
                        # health check until there is nothing to do. This is okay, because when
                        # mails are delivered, everything seems to be okay. When there is an
                        # issue and we have to wait anyway, we can perform a health check to let
                        # the monitoring sooner or later know.
                        self.smtp_delivery.do_health_check()
                        time.sleep(30)

            except queue.Empty:
                self.l.debug(
                    "_do_smtp_delivery(): No SMS in queue. Checking if health check should be run."
                )
                self.smtp_delivery.do_health_check()
            except Exception as e:
                self.l.warning("Got exception.")
                print(e)
            except:
                self.l.warning("_do_smtp_delivery(): Unknown exception.")
                traceback.print_exc()

    def _init_pool(self) -> bool:
        """
        Initializes the modem pool.
        @return: Returns True on success or False if there was an error with the modem configuration.
        """
        health_check_interval = self.config.getint(
            "modempool", "health_check_interval", fallback=600
        )
        self.pool = modempool.ModemPool(health_check_interval)
        self.pool.set_event_thread(self.event_available)

        sim_config = SmsGate.read_sim_config()

        self.l.info("Initializing modem pool.")

        for identifier in sim_config.sections():

            # read config
            modem_conf = modemconfig.read_modem_config(identifier, sim_config,
                                                       self.config.get("modempool", "sms_self_test_interval",
                                                                       fallback=""))

            if not modem_conf.verify():
                self.l.error(
                    f"[{identifier}] There is a problem in the modem configuration."
                )
                return False

            self.l.debug(f"[{identifier}] Modem configuration is {modem_conf}.")
            gsmmodem = None

            if modem_conf.enabled:
                # set up modem
                self.l.info(f"[{identifier}] Initializing modem {identifier}.")
                for i in range(0, 3):
                    try:
                        gsmmodem = modem.Modem(identifier, modem_conf, self.config.get("modempool", "serial_ports_hint_file"))
                        if gsmmodem:
                            gsmmodem.set_event_thread(
                                self.event_available
                            )  # modem sets an event
                            break
                        else:
                            self.l.warning(
                                f"[{identifier}]. Initialization failed. Wait before reinitializing modem."
                            )
                            time.sleep(10)
                    except:
                        the_type, the_value, the_traceback = sys.exc_info()
                        self.l.warning(
                            f"[{identifier}]. Unexpected exception: {the_type} {the_value} {the_traceback}"
                        )

                # add modem if enabled
                self.pool.add_modem(gsmmodem)

        self.l.info("Modem pool initialized.")
        return True

    def run(self) -> None:
        """
        The run loop that won't return.
        The method waits for events, checks for incoming SMS that should be forwarded via SMTP, it also checks for
        outgoing SMS and triggers health checks.
        """
        while True:

            self.event_available.clear()

            self.l.info("Waiting for next event ...")
            if self.event_available.wait(
                    timeout=self.config.getint(
                        "modempool", "health_check_interval", fallback=600
                    )
            ):

                # This code is executed either when an SMS was received
                # or at a timeout.
                self.event_available.clear()
                self.l.info(f"Event received. Check for incoming SMS.")

                # process incoming SMS
                sms = self.pool.get_incoming_sms()
                if sms:
                    self.l.info(f"[{sms.get_id()}] Got incoming SMS")

                    assert self.smtp_delivery_thread is not None
                    assert self.smtp_delivery_thread.is_alive()

                    if self.config.getboolean("mail", "enabled", fallback=True):
                        self.l.debug(f"[{sms.get_id()}] Put SMS into outgoing queue.")
                        self.smtp_delivery_queue.put(sms)

                else:
                    self.l.info("No incoming SMS")

                # process outgoing SMS
                self.l.info("Try processing outgoing SMS (if available) ...")
                self.pool.process_outgoing_sms()
                self.l.info("Outgoing SMS processed.")

            else:
                # trigger health check
                self.l.info("Check for health check ...")
                self.pool.do_health_check()


def setup_seccomp(log_only: bool = False) -> None:
    """
    Enable SECCOMP filtering.
    @param log_only: A boolean flag indicating that violations are only logged.
    """
    l = logging.getLogger("SECCOMP")
    try:
        import pyseccomp as seccomp
        import errno

        action_deny = seccomp.ERRNO(errno.EACCES)

        f = seccomp.SyscallFilter(seccomp.LOG if log_only else action_deny)
        f.set_attr(seccomp.Attr.CTL_LOG, 1)

        allowed_syscalls = [
            "accept4",
            "access",
            "arch_prctl",
            "bind",
            "brk",
            "clone",
            "close",
            "connect",
            "dup",
            "epoll_create1",
            "epoll_ctl",
            "epoll_wait",
            "exit",
            "fcntl",
            "flock",
            "fstat",
            "futex",
            "getcwd",
            "getdents",
            "getdents64",
            "getpid",
            "getrandom",
            "getsockname",
            "getsockopt",
            "getpeername",
            "gettid",
            "ioctl",
            "listen",
            "lseek",
            "lstat",
            "madvise",
            "mmap",
            "mprotect",
            "munmap",
            "openat",
            "pipe2",
            "poll",
            "prctl",
            "pread64",
            "prlimit64",
            "recvfrom",
            "recvmsg",
            "read",
            "readlink",
            "rt_sigaction",
            "rt_sigprocmask",
            "seccomp",
            "select",
            "sendmmsg",
            "sendto",
            "setsockopt",
            "set_robust_list",
            "set_tid_address",
            "shutdown",
            "sigaltstack",
            "socket",
            "stat",
            "sysinfo",
            "uname",
            "wait4",
            "write"
        ]

        for sc in allowed_syscalls:
            l.debug(f"Allow syscall {sc}.")
            f.add_rule(seccomp.ALLOW, sc)

        f.load()

        l.info(f"Enabled SECCOMP (log_only: {log_only}).")

    except ImportError:
        l.warning("Failed to use SECCOMP.")

def main() -> None:
    """
    The main function that launches the SMS Gateway server. It will not return.
    """

    # read config
    server_config = SmsGate.read_config()

    # set umask
    os.umask(0o007)

    log_level = logging.getLevelName(server_config.get("logging", "level", fallback="INFO").upper())

    # configure logging
    root = logging.getLogger()
    root.setLevel(log_level)

    cons_handler = logging.StreamHandler(sys.stdout)
    cons_handler.setLevel(log_level)
    cons_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    )
    root.addHandler(cons_handler)

    # apply seccomp
    if server_config.getboolean("seccomp", "enabled", fallback=True):
        setup_seccomp()

    # check config file permissions
    helper.check_file_permissions("conf/sim-cards.conf")
    helper.check_file_permissions("conf/smsgate.conf")

    # launch service
    sms_gate = SmsGate(server_config)
    sms_gate.run()


if __name__ == "__main__":
    main()
