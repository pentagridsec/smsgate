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
import binascii
import datetime
import glob
import logging
import queue
import random
import re
import sys
import threading
import time
import traceback
import uuid
from typing import Optional, List, Tuple

import serial
from gsmmodem.exceptions import (
    TimeoutException,
    PinRequiredError,
    IncorrectPinError,
    GsmModemException,
    CmeError,
    CmsError,
)
from gsmmodem.modem import GsmModem, SerialComms, SentSms, ReceivedSms

import modemconfig
import sms
import serialportmapper


class Modem(threading.Thread):
    def __init__(self, identifier: str, modem_config: modemconfig.ModemConfig, serial_ports_hint_file: str) -> None:
        assert identifier is not None
        self.event_available = None
        self.identifier = identifier
        self.modem_config = modem_config
        self.serial_ports_hint_file = serial_ports_hint_file

        self.balance = None
        self.sms_receiver_queue = queue.Queue()
        self.sms_sender_queue = queue.Queue()
        self.sent_sms = {}  # a dict of sent SMS; value is an SMS object

        self.last_health_check = None
        self.health_state = "OK"
        self.health_logs = None
        self.health_check_expected_token = None

        self.modem = None
        self.current_port = None
        self.status = None
        self.init_counter = 0
        self.last_init = datetime.datetime.now(tz=None)
        self.last_received = None
        self.last_sent = None

        self.l = logging.getLogger(f"Modem [{identifier}]")

        self.current_network = None
        self.current_signal = 0

        threading.Thread.__init__(self)
        self.start()

    def get_identifier(self) -> str:
        """
        Get the modem name.
        @return: Returns the modem identifier as string.
        """
        return self.identifier

    def get_prefixes(self) -> List[str]:
        """
        Get the phone prefixes that this modem is responsible for.
        For each modem, it is possible to define a list of phone number prefixes like "+49172", "+49", that this modem
        is responsible for. If you have multiple SIM cards, it allows you to do routing decisions.
        @return: Returns a list of phone number prefixes for a modem.
        """
        return self.modem_config.prefixes

    def get_costs(self) -> float:
        """
        Get costs for sending a single SMS.
        This information is used for routing decisions. It is just a number and not strictly related to a currency, but
        usually refers to the currency that is mentioned in the ModemConfig.
        @return: Returns the costs per SMS.
        """
        return self.modem_config.costs_per_sms

    def get_phone_number(self) -> str:
        """
        Get the phone numer associated with a modem.
        Per convention phone numbers are entered everywhere in E.123 international notation.
        @return: Returns the phone number as string.
        """
        return self.modem_config.phone_number

    def set_event_thread(self, event_available: threading.Event) -> None:
        """
        Pass a threading.Event object to Modem object to get notified about incoming SMS.
        @param event_available: a threading.Event object to signal between threads. For an incoming SMS, the event
            object's method set() is called.
        """
        self.event_available = event_available

    def get_balance(self) -> float:
        """
        Returns the modem's SIM card account balance.
        @return: Returns the account balance as float or None, if the balance is not known (yet).
        """
        return self.balance

    def get_currency(self) -> str:
        """
        Returns the modem's SIM card account balance currency.
        @return: A string indicating the currency, for example "EUR" or "CHF".
        """
        return self.modem_config.ussd_currency

    def get_current_network(self) -> Optional[str]:
        """
        Get the current network name that a modem is using.
        @return: Returns the network name as string, for example "Vodafone".
        """
        return self.current_network

    def get_current_signal_rssi(self) -> int:
        """
        Get the received signal strength indicator (RSSI) value.
        The value is requested via the 'AT+CSQ' command.
        @return: Returns the signal strength as a value between 0 and 00, or -1 if it is unknown.
        """
        return self.current_signal

    def get_modem_config(self) -> modemconfig.ModemConfig:
        """
        Get the modem configuration
        @return: Returns the config as ModemConfiguration object.
        """
        return self.modem_config

    def get_current_signal_dB(self) -> int:
        """
        Get the signal strength as dBm value (decibel referring to mW).
        The RSSI maps to dBm as below:
        0 113 dBm or less
        1 111 dBm
        2...30 109... 53 dBm
        31 51 dBm or greater
        99 not known or not detectable
        Here is a detailed table: https://m2msupport.net/m2msupport/atcsq-signal-quality/
        @return: An int value representing a dBm value.
        """
        i = self.current_signal
        if 2 <= i <= 30:
            return [
                -109,
                -107,
                -105,
                -103,
                -101,
                -99,
                -97,
                -95,
                -93,
                -91,
                -89,
                -87,
                -85,
                -83,
                -81,
                -79,
                -77,
                -75,
                -73,
                -71,
                -69,
                -67,
                -65,
                -63,
                -61,
                -59,
                -57,
                -55,
                -53,
            ][i - 2]
        elif i >= 31:
            return -51
        else:
            return -113

    def get_port(self) -> Optional[str]:
        """
        Get the device file name for the modem's serial port.
        @return: Returns a string with the serial port name or None, if there is no port known (yet).
        """
        return self.current_port

    def get_status(self) -> Optional[str]:
        """
        Get a textual string representing the current state of the modem in human-readbale form.
        @return: Returns a message indicating the modem's current state. Value may be None.
        """
        return self.status

    def get_init_counter(self) -> int:
        """
        Get the counter for modem initialisations.
        Each time a modem is initialized, the counter gets increased. An initialisation happens or is necessary after
        internal errors or at server startup. Therefore, the counter indicates there is an issue that results in
        reinitialisations and it is observable in comparison with other modem objects.
        @return: Returns a counter how many modem initialisations happened during the server uptime.
        """
        return self.init_counter

    def get_last_init(self) -> datetime.datetime:
        """
        Get the timestamp of the last initialisation.
        @return: Returns the last initialisation as datetime object.
        """
        return self.last_init

    def get_last_received(self) -> Optional[datetime.datetime]:
        """
        Get the timestamp of the last received SMS.
        @return: Returns the timestamp of the last received SMS as datetime object or None.
        """
        return self.last_received

    def get_last_sent(self) -> Optional[datetime.datetime]:
        """
        Get the timestamp of the last sent SMS.
        @return: Returns the timestamp of the last sent SMS as datetime object or None.
        """
        return self.last_sent

    def _handle_sms(self, _sms: ReceivedSms) -> None:
        """
        Handle incoming SMS from the python-gsmmodem-new layer.
        The _sms parameter is a gsmmodem.modem.ReceivedSms.
        """

        self.l.info("== SMS message received ==")

        self.last_received = datetime.datetime.now(tz=None)

        # first check if we sent the SMS to ourself
        if (
                self.health_check_expected_token
                and self.health_check_expected_token in _sms.text
        ):
            self.l.info("Modem received expected health SMS")
            # clear value
            self.health_check_expected_token = None

        new_sms = sms.SMS(
            sms_id=None,
            recipient=self.modem_config.phone_number,
            text=_sms.text,
            sender=_sms.number,
            timestamp=_sms.time,
            receiving_modem=self,
        )

        # Only log SMS in debug mode and then without content
        self.l.debug(new_sms.to_string(content=False))

        self.l.info(f"Put SMS in queue.")
        self.sms_receiver_queue.put(new_sms)
        self.event_available.set()

    def get_sms(self) -> sms.SMS:
        """
        Get incoming SMS.
        @return: Returns an SMS object that is in the local SMS Queue. If there is no element in the queue, a
            queue.Empty exception is thrown, because the Python Queue class is used as underlying object.
        """
        return self.sms_receiver_queue.get(block=False)

    def has_sms(self) -> bool:
        """
        Check if there is an SMS available in the incoming queue.
        @return: Returns True or False.
        """
        return not self.sms_receiver_queue.empty()

    def _check_balance_thresholds(self) -> Tuple[str, Optional[str]]:
        """
        Check if account balance does not fall below warning or critical thresholds.
        When using prepaid SIM cards, there must be enough balance to be able to send SMS. Even if one "only" like to
        receive SMS, operators want to see financial events for SIM card to see if a SIM card is still active, which
        means it is necessary to trigger billable events from time to time. It is therefore necessary to check if there
        is enough budget available.
        @return: Returns the check result as tuple State, Message. State is either "OK", "WARNING", or "CRITICAL".
            Message is a human-readable string giving details about the issue. Message may be a None.
        """
        assert (
                self.modem_config.account_balance_critical <= self.modem_config.account_balance_warning
        )

        if self.balance < self.modem_config.account_balance_critical:
            s = f"Modem[{self.identifier}]: Critical: Account balance of {self.balance} {self.modem_config.ussd_currency} " \
                f"is lower than threshold of {self.modem_config.account_balance_critical} {self.modem_config.ussd_currency}."
            self.l.warning(s)
            return "CRITICAL", s

        elif self.balance < self.modem_config.account_balance_warning:
            s = f"Modem[{self.identifier}]: Warning: Account balance of {self.balance} {self.modem_config.ussd_currency} " \
                f"is lower than threshold of {self.modem_config.account_balance_warning} {self.modem_config.ussd_currency}."
            self.l.warning(s)
            return "WARNING", s

        else:
            return "OK", None

    def send_sms(self, _sms: sms.SMS) -> None:
        """
        Use the modem to send an SMS.
        @param _sms: An SMS object of type sms.SMS, which is sent by the modem. Use get_delivery_status() to check the
            delivery status.
        """
        self.sms_sender_queue.put(_sms)
        self.last_sent = datetime.datetime.now(tz=None)

    def get_delivery_status(self, sms_id: str) -> bool:
        """
        Returns the delivery status for an SMS referenced by a UUID.
        @param sms_id: The SMS' UUID. Each sms.SMS object has a UUID and the modem object keeps track of sent SMS as
            long as the server is up and running. You can check the delivery status for a UUID.
        @return: Returns True or False. If the UUID is unknown, False is returned.
        """

        if (
                sms_id in self.sent_sms
                and self.sent_sms[sms_id].status == SentSms.DELIVERED
        ):
            return True
        return False

    def cleanup(self, sms_id: str) -> bool:
        """
        Clean up sent datastructure and remove information regarding 'sms_id'.
        This function is called by the modempool during the modem pool clean up to get rid of old data.
        @param sms_id: The SMS' UUID. The modempool also knows which SMS were sent.
        @return: Returns True or False. If the UUID is unknown, False is returned.
        """

        if sms_id in self.sent_sms:
            del self.sent_sms[sms_id]
            return True

        return False

    def get_health_state(self) -> Tuple[str, Optional[str]]:
        """
        Get the health state.
        @return: Returns the modem's internal health state as tuple of State, Message. State is either "OK", "WARNING",
            or "CRITICAL". Message is a human-readable string giving details about the issue. Message may be a None.
        """
        return self.health_state, self.health_logs

    def _do_health_check(self, do_now: bool = False) -> None:
        """
        Internal method that potentially triggers a health check.
        This method checks if performing a health check is necessary and will act accordingly.
        @param do_now: Boolean flag to force a health check.
        """
        if ((self.last_health_check is None)
            or do_now
            or (self.health_state != "OK")
            or ((datetime.datetime.now() - self.last_health_check).total_seconds()
                    >= self.modem_config.health_check_interval)):
            self.health_state, self.health_logs = self._really_do_health_check()

    def _repeat_initialization(self) -> None:
        """
        Repeat initialisation until it is successful.
        """
        while not self._init_modem():
            self.l.error(
                f"Initialization failed. Timeout occurred. This may mean, the modem was lost. Reinitializing modem."
            )
            self._do_health_check(do_now=True)
            time.sleep(30)

    def _find_port(self, device_name: str, expected_imei: str) -> Optional[str]:
        """
        Looks up a serial port identified by a full name or a glob and returns the serial port name.

        When using USB devices of the same USB vendor ID and product ID, the
        order of devices is not fixed and the names are not always the same.
        For example modem slot 00 could be /dev/ttyACM0, but also /dev/ttyACM3
        or any other. On the other side, we may have a real RS232 serial modem,
        which always has the same name. Therefore, we implement a lookup and
        find modems corresponding to SIM cards identified via the modem's IMEI.

        Checking the modem device here during the initialization allows us to
        reinitialize a modem also later during runtime. When the modem is
        initialized, the code checks which device should be opened. Since each thread
        does this check, there is a bit of overhead.
        @param device_name: The serial port's device file name as string. The value may contain a wildcard. If a
            wildcard is used, the modem probes for a device file names and used the IMEI to find a port. If the port
            name is fixed, the function itself does no IMEI check.
        @param expected_imei: There is a configuration entry for each modem that references the IMEI as string. The
            IMEI is the International Mobile Equipment Identity a unique ID for the modem hardware. This parameter is
            necessary to find the correct serial device.
        @return: Returns the device file name as string or None, if it was not found.
        """

        # Case 1: Device name is fixed
        if not device_name.endswith("*"):
            return device_name

        # Wait a random time, because otherwise all threads will look up their devices at the same time.
        time.sleep(random.randint(0, 15))

        # Case 2: Port is known
        spm = serialportmapper.SerialPortMapper(self.serial_ports_hint_file)
        port = spm.get_mapping(expected_imei)
        if port:
            if not self._port_was_renumbered(port):
                return port

        # Case 3: Find port
        device_list = glob.glob(device_name)
        random.shuffle(device_list)

        for f in device_list:
            self.l.info(f"Try to find correct port. Will open {f}.")
            self.status = f"Try port {f}."

            if self._check_imei(f, self.modem_config.baud, expected_imei):
                self.status = f"Port {f} found."
                return f

        self.l.error(f"Can't find modem with IMEI {expected_imei}")
        return None

    def _check_imei(self, port: str, baud: int, expected_imei: str) -> bool:
        """
        Check if the modem behind a certain port is the one with an expected IMEI.
        The function opens the serial port and asks the modem for the IMEI via AT+CGSN, which is than compared to the
        expected_imei.
        In addition, every information about IMEI to serial port mapping is stored in the SerialPortMapper instance to
        speed up lookups.
        @param port: The serial port of the modem given as device file name.
        @param baud: The symbol rate for the device file name as int, such as 9600 or 115200.
        @param expected_imei: A string with the expected IMEI.
        @return: Returns True if the modem behind a serial port has the given IMEI. Otherwise False is returned. In
            case of communication errors, None is returned.
        """
        modem = None
        try:
            modem = SerialComms(port, baud, exclusive=True)
            assert modem
            modem.connect()

            self.l.debug(f"Expected IMEI of modem: {expected_imei}")

            for i in range(0, 5):
                try:
                    modem.write("AT&F\r\n")
                    modem.write("AT&F\r\n")
                    modem.write("AT&F\r\n")
                    modem.write("ATZ\r\n")
                    modem.write("ATZ\r\n")
                    modem.write("ATZ\r\n")
                    modem.write("ATE0\r\n")  # disable echo
                    modem.write("AT&W\r\n")  # save

                    found_imei = modem.write("AT+CGSN\r\n")[0]
                    self.l.info(f"Read IMEI of modem    : {found_imei}")

                    if expected_imei is not None:
                        spm = serialportmapper.SerialPortMapper(self.serial_ports_hint_file)
                        if expected_imei == found_imei:
                            spm.set_mapping(found_imei, port)
                            self.l.info(f"Modem found on serial port {port}.")
                            modem.close()
                            return True
                        elif re.match(r"^\d+$", found_imei):
                            spm.set_mapping(found_imei, port)
                            self.l.debug(f"Unexpected modem at port {port}.")
                            modem.close()
                            return False
                        else:
                            self.l.debug(
                                f"Unexpected answer from modem at port {port}."
                            )

                except TimeoutException:
                    pass

            modem.close()

        except serial.serialutil.SerialException as e:
            self.l.error("_check_imei: Got exception: " + str(e))
            # We do not have a modem object here. Therefore, there is nothing to close.
        except GsmModemException as e:
            self.l.error("_check_imei: Got exception: " + str(e))
            modem.close()
        return False

    def _port_was_renumbered(self, use_port: str = None) -> bool:
        """
        Check if serial devices were renumbered.
        @return: Returns False if the known serial port still matches the expected IMEI and True else.
        """

        if use_port is not None:
            p = use_port
        else:
            p = self.current_port

        if p:
            # We have a port, which means it is not the first run. However, when there is
            # a re-initialisation after a modem power-loss, we just check the IMEI again,
            # because devices might be renumbered.
            self.status = "Check port renumbering."
            imei_status = self._check_imei(p, self.modem_config.baud, self.modem_config.imei)
            if imei_status:
                return False
            else:
                # There was a renumbering of ports, better we search again
                self.status = "Port was renumbered. Reinitializing."
                self.current_port = None

        return True

    def _init_modem(self) -> bool:
        """
        Initialize the modem object by finding the correct port, opening the serial device, passing the SIM card PIN
        and so on.
        @return: Returns the initialisation status as True or False.
        """

        # reset data
        self.current_network = None
        self.current_signal = 0

        self.status = "Try to initialize modem."
        self.l.info(f"Initializing modem {self.identifier}.")
        try:

            self._port_was_renumbered()

            if self.current_port is None:
                self.status = "Try finding port."
                self.current_port = self._find_port(self.modem_config.port, self.modem_config.imei)

            if self.current_port is None:
                self.status = "Failed finding port."
                self.l.error(
                    f"Problem: Can't find a port {self.modem_config.port} that matches IMEI {self.modem_config.imei}."
                )
                return False

            self.status = f"Finally initializing port {self.current_port}."
            time.sleep(10)
            self.modem = GsmModem(
                self.current_port,
                self.modem_config.baud,
                smsReceivedCallbackFunc=self._handle_sms,
                exclusive=True,
            )  # was True
            self.modem.log = logging.getLogger(f"Modem [{self.identifier}]")
            self.status = f"Port {self.current_port} sucessfully opened."

        except GsmModemException as e:
            self.l.error("_check_imei: Got exception: " + str(e))
            self.status = "Check port renumbering - Exception."
            return False

        self.modem.smsTextMode = False

        self.l.debug(f"Connecting to GSM modem on {self.current_port}.")
        self.status = "Connecting to modem."

        try:
            assert self.modem_config.pin is None or int(self.modem_config.pin) >= 0
            self.modem.connect(
                self.modem_config.pin,
                waitingForModemToStartInSeconds=self.modem_config.wait_for_start,
            )

        except PinRequiredError:
            self.l.error(f"Error: SIM card PIN required. Please specify a PIN.")
            self.status = "Error: SIM PIN required."
            self.modem.close()
            return False

        except IncorrectPinError:
            self.l.error(
                f"Error: Incorrect SIM card PIN entered. Stopping program to not accidentally enter it twice."
            )
            self.status = "Error: Incorrect SIM PIN."
            self.modem.close()
            sys.exit(1)

        except serial.serialutil.PortNotOpenError as e:
            self.l.error(f"Error: Failed to open serial connection.")
            self.status = "Error finally opening port."
            self.l.error(e)
            return False

        self.l.debug(f"Checking for network coverage...")

        max_try = 10
        for i in range(0,max_try):
            self.status = f"Waiting for network ({i}/{max_try})."
            try:
                self.modem.waitForNetworkCoverage(120)
                self.status = "Network found."
            except TimeoutException:
                self.l.error(f"Error: Failed to connect to network. Bad signal?")
                self.status = "Error: Failed to connect to network."
                self.modem.close()
                return False

        self._delete_sms()

        # We do not check the balance immediately, but wait a bit.
        # self.check_balance()

        self.status = "Ready."
        self.init_counter += 1
        self.last_init = datetime.datetime.now(tz=None)

        self.health_state = "OK"
        self.health_logs = None

        return True

    def set_ready(self) -> None:
        """
        Set human-readable status message to "Ready."
        """
        self.status = "Ready."

    def _delete_sms(self, all:bool=False) -> None:
        # Delete all unread/unset stored SMS
        try:
            if all:
                self.modem.write("AT+CMGD=,4\r\n")
            else:
                self.modem.write("AT+CMGD=,2\r\n")
        except CmsError:
            self.l.warning("Exception: Failed to delete SMS.")

    def _send_ussd_ucs2(self, code: str) -> str:
        """
        Send USSD code in UCS2 format.
        @param code: The clear-text code to send.
        @return: Returns the decoded response as string.
        """
        self.l.debug("Set encoding UCS2.")
        self.modem.smsEncoding = "UCS2"

        # transform input to UCS2-encoding
        code_ucs2 = (
            binascii.hexlify(bytearray(code.encode("utf-16-be")))
            .decode("utf-8")
            .upper()
        )
        self.l.debug(f"Send USSD Code [UCS2:{code_ucs2},plain:{code}].")

        response = self.modem.sendUssd(code_ucs2, responseTimeout=30)
        decoded_response = binascii.unhexlify(response.message).decode("utf-16-be")

        # There was one case, where the Euro currency sign was encoded as
        # GSM 7-bit Basic Character Set Extension, which triggers a problem
        # when passed via XML and then parsed. Therefore, we use a work-around
        # here.
        decoded_response = decoded_response.replace("\x1b\x65", "€")

        self.l.debug(f"Decoded USSD response is [{decoded_response}]")

        self.set_ready()
        return decoded_response

    def _send_ussd_enc(self, code: str, encoding: str) -> str:
        """
        Send USSD code in a certain encoding, but passing it as ASCII without transformation.
        The function is used for testing and debugging.
        @param code: The clear-text code to send in ASCII.
        @param encoding: The encoding to use, without processing the input.
        @return: Returns the decoded response as string.
        """
        self.l.debug(f"Set encoding {encoding}.")
        self.modem.smsEncoding = encoding

        self.l.debug(f"Send USSD Code [{encoding}:{code}].")
        response = self.modem.sendUssd(code, responseTimeout=30).message
        self.l.debug(f"USSD response is [{response}]")
        self.set_ready()
        return response

    def send_ussd(self, code: str) -> Optional[str]:
        """
        Send an USSD code and wait for response.
        @param code: The clear-text code to send.
        @return: Returns the decoded response as string or None in case of an error.
        """
        self.status = "Send USSD."
        try:

            if self.modem_config.encoding == "UCS2" or self.modem_config.encoding is None:
                return self._send_ussd_ucs2(code)
            else:
                return self._send_ussd_enc(code, self.modem_config.encoding)

        except TimeoutException:
            self.l.error(
                f"Error: Failed to send USSD message. Got TimeoutException. Retry."
            )
            # self.send_ussd(code, 'GSM', counter + 1)
            return None
        except CmeError:
            self.l.error(f"Error: Failed to send USSD message. Got CmeError. Retry.")
            # self.send_ussd(code, 'GSM', counter + 1)
            return None

    def request_online_balance(self) -> Optional[float]:
        """
        Request account balance and get the balance as value, if possible.
        Currently, only balance checks via USSD codes are supported. Some providers do not support this, for example
        O2 in Germany.
        @return: Returns the balance as float. None is returned on error or if the balance information is not available.
        """

        if not self.modem_config.ussd_account_balance:
            return None

        try:

            response = self.send_ussd(self.modem_config.ussd_account_balance)
            if response is None:
                self.l.debug(f"USSD response is None. Stop processing.")
                return None

            self.l.debug(f"Applying regexp [{self.modem_config.ussd_account_balance_regexp}]")

            if self.modem_config.ussd_account_balance_regexp is None:
                self.l.warning("Regexp for extracting the balance from the USSD response is not set. Do not process "
                               "USSD response any further.")
                return None

            result = re.search(self.modem_config.ussd_account_balance_regexp, response)
            if result:
                balance = result.group(1)
                self.l.debug(f"Balance as string: {balance} {self.get_currency()}")
                balance = balance.replace(",", ".")
                self.balance = float(balance)
                self.l.debug(f"Balance as float: {self.balance} {self.get_currency()}")

                return self.balance
            else:
                self.l.error(f"Error: Regular expression [{self.modem_config.ussd_account_balance_regexp}] " +
                             f"failed for string [{response}]")
        except TimeoutException:
            self.l.error("Error: Failed to send USSD message.")

        return None

    def _do_send_sms(self, _sms: sms.SMS) -> bool:
        """
        Internal function to send SMS.
        @param _sms: An SMS object of type sms.SMS.
        @return: Returns either True or False. True means the SMS was accepted for delivery. You may want to check the
            delivery status explicitly.
        """
        try:
            # sendSms returns a SentSms object
            self.status = "Send SMS."
            self.sent_sms[_sms.get_id()] = self.modem.sendSms(
                _sms.get_recipient(), _sms.get_text(), waitForDeliveryReport=False
            )
            return True
        except TimeoutException:
            self.l.error(f"Error: Failed to send SMS.")

        return False

    def print_info(self) -> None:
        """
        Print information about a modem such as used serial port, IMEI, IMSI, SMSC, network operator, signal quality.
        """
        assert self.modem

        self.current_network = self.modem.networkName
        self.current_signal = self.modem.signalStrength

        if self.current_network:
            self.current_network = self.current_network.strip()

        self.l.info(
            f"--------------------------------------------------------------------"
        )
        self.l.info(f"Modem port        : " + (self.current_port or "N/A"))
        self.l.info(f"Modem manufacturer: " + (self.modem.manufacturer or "N/A"))
        self.l.info(f"Modem model       : " + (self.modem.model or "N/A"))
        self.l.info(f"Modem revision    : " + (self.modem.revision or "N/A"))
        self.l.info(f"IMEI              : " + (self.modem.imei or "N/A"))
        self.l.info(f"IMSI              : " + (self.modem.imsi or "N/A"))
        self.l.info(f"SMSC              : " + (self.modem.smsc or "N/A"))
        self.l.info(f"Phone number      : " + (self.modem.ownNumber or "N/A"))
        self.l.info(f"Network           : " + (self.current_network or "N/A"))
        self.l.info(f"Signal strength   : " + str(self.current_signal))
        self.l.info(f"SMS Encoding      : " + (self.modem.smsEncoding or "N/A"))

    def _really_do_health_check(self) -> Tuple[str, Optional[str]]:
        """
        Internal health check implementation. It checks if the modem is connected to a network, parameters are in
        range, balance is in acceptable range. At certain intervals defined in the ModemConfig, a test SMS is sent the
        own number to check if that works and also to generate a financial event to keep the SIM card alive.
        @return: Returns the modem's internal health state as tuple of State, Message. State is either "OK", "WARNING",
            or "CRITICAL". Message is a human-readable string giving details about the issue. Message may be a None.
        """
        self.l.info(f"Run health check for modem.")
        self.last_health_check = datetime.datetime.now()

        if self.modem is None:
            if self.modem_config.enabled:
                return "CRITICAL", f"{self.identifier} No modem object."
            else:
                return "WARNING", f"{self.identifier} No modem object."

        if self.modem.manufacturer is None:
            return (
                "CRITICAL",
                f"{self.identifier} Failed to communicate with modem to detect manufacturer.",
            )

        if not self.modem.imsi:
            return "CRITICAL", f"{self.identifier} There is no IMSI."

        if not self.modem.smsc:
            return "CRITICAL", f"{self.identifier} No SMSC set."

        s = self.modem.signalStrength
        if s == -1:
            return "WARNING", f"{self.identifier} Unknown signal strength."

        if s <= 1:
            return "CRITICAL", f"{self.identifier} Weak signal strength."

        if s <= 5:
            return "WARNING", f"{self.identifier} Weak signal strength."

        # Account balance checks fail frequently, therefore this check only results in warnings
        # with valid balances.

        if self.modem_config.ussd_account_balance and self.modem_config.ussd_account_balance_regexp:

            #    if self.check_balance() is None:
            #        return "WARNING", f"{self.identifier} Failed to check balance."

            if self.request_online_balance() is not None:
                if self.balance is not None:
                    level, log = self._check_balance_thresholds()
                    if level != "OK":
                        return level, log

        # At certain intervals send an SMS to ourself
        now = datetime.datetime.now()
        day_matches = False

        if self.modem_config.sms_self_test_interval == "monthly":
            if now.day == 1:
                day_matches = True

        elif self.modem_config.sms_self_test_interval == "weekly":
            if now.weekday == 1:
                day_matches = True
        else: # Third option is daily
            day_matches = True

        if day_matches:

            seconds_since_midnight = (
                    now - now.replace(hour=0, minute=0, second=0, microsecond=0)
            ).total_seconds()
            self.l.info(f"Day for the SMS self test matches. There are {seconds_since_midnight} seconds since midnight.")

            if seconds_since_midnight <= self.modem_config.health_check_interval:
                # Have checked balance thresholds before, not necessarily the online-balance,
                # but the last balance value we have seen and stored.
                self.l.info("Send test SMS to ourself.")
                self._send_test_sms()

            elif (
                    self.health_check_expected_token
                    and seconds_since_midnight <= 2 * self.modem_config.health_check_interval
            ):
                # The expected token was not cleared, which means the expected SMS was not received.
                # Therefore, we send another SMS
                self.l.info(
                    "Send second test SMS to ourself, because last one was not received."
                )
                self._send_test_sms()

            elif self.health_check_expected_token:
                self.l.info("Failed to receive the test SMS. There is a problem.")
                return (
                    "WARNING",
                    f"{self.identifier} Failed to send test SMS to oneself.",
                )

        self.status = "Ready."
        return "OK", None

    def _send_test_sms(self) -> None:
        """
        Generate a UUID and send it as test SMS to the own number.
        """
        new_uuid = str(uuid.uuid4())
        self.health_check_expected_token = "health-check-" + new_uuid
        return self.send_sms(
            sms.SMS(
                sms_id=new_uuid,
                recipient=self.modem_config.phone_number,
                text=self.health_check_expected_token,
                sender=self.modem_config.phone_number,
            )
        )

    def close(self) -> None:
        """
        Closes the serial connection to the modem.
        """
        if self.modem:
            # if self.modem.alive:
            self.modem.close()
        self.modem = None

    def run(self) -> None:
        """
        Modem run loop
        """

        while True:

            try:
                # initialize modem if necessary
                if self.modem is None:
                    self._repeat_initialization()
                    self.print_info()

                self.l.debug("Wake up.")
                try:
                    # Wait for SMS or for a timeout
                    _sms = self.sms_sender_queue.get(timeout=60)
                    self._do_send_sms(_sms)
                except queue.Empty:
                    pass
                
                # start a health check?
                self._do_health_check()

            except (
                    TimeoutException,
                    serial.serialutil.PortNotOpenError,
                    Exception,
            ) as e:
                self.l.error(
                    "Timeout occurred or modem lost. Reinitializing modem. Exception was:"
                    + str(e)
                )
                traceback.print_exc()
                self.status = "Timeout."
                self.close()

                self._do_health_check(do_now=True)
