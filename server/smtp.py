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

import datetime
import logging
import smtplib
import ssl
from email.mime.text import MIMEText
from typing import Tuple

from sms import SMS


class SMTPDelivery:
    def __init__(
        self, host: str, port: int, user: str, password: str, health_check_interval: int
    ) -> None:
        """
        Create a new SMTPDelivery object.
        This class handles the delivery of SMS via SMTP and it supports health checks.

        @param host: The mail server host.
        @param port: The SMTP server port. STARTSSL or plaintext communication is not supported.
        @param user: The username for SMTP authentication.
        @param password: The password for SMTP authentication.
        @param health_check_interval: The interval for the health check in seconds.
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.server = None

        self.last_health_check = datetime.datetime.now()
        self.health_check_interval = health_check_interval
        self.health_state = "OK"
        self.health_logs = None

        self.l = logging.getLogger("SMTPDelivery")

        if port == 25:
            error_msg = "The client does not support STARTTLS"
            self.l.error(error_msg)
            self.health_state = "CRITICAL"
            self.health_logs = error_msg

    def _create_connection(self) -> None:
        """
        Set up a connection to the SMTP server using TLS.
        """
        context = ssl.create_default_context()

        # There is an option to disable certain TLS mechanisms, therefore we do it.
        context.options |= ssl.OP_NO_SSLv2
        context.options |= ssl.OP_NO_SSLv3
        context.options |= ssl.OP_NO_TLSv1
        context.options |= ssl.OP_NO_TLSv1_1

        self.server = smtplib.SMTP_SSL(self.host, self.port, context=context)
        self.l.info(f"Try to log in as {self.user}")
        self.server.login(self.user, self.password)
        self.l.info(f"Log in was successful.")

    def get_health_state(self) -> Tuple[str, str]:
        """
        Get the SMTP module's last measured health state.
        @return: The function returns a string tuple. The first element is either
            "OK", "WARNING" or "CRITICAL" and indicates the health state. The most severe level is reported. The
            second element is a string-concatenation of log messages or maybe an empty string if everything is okay.
        """
        return self.health_state, self.health_logs

    def do_health_check(self) -> Tuple[str, str]:
        """
        Check if a health check is necessary and potentially perform a health check.
        @return: The function returns a string tuple. The first element is either
            "OK", "WARNING" or "CRITICAL" and indicates the health state. The most severe level is reported. The
            second element is a string-concatenation of log messages or maybe an empty string if everything is okay.
        """
        now = datetime.datetime.now()
        if (now - self.last_health_check).total_seconds() >= self.health_check_interval:

            self.last_health_check = datetime.datetime.now()
            self.l.info("Collecting health check infos from SMTP server.")

            for i in range(1, 3):
                try:

                    if self.server is None:
                        self._create_connection()

                    if self.server is not None:
                        self.server.noop()

                    # Not crashed yet? Reset error state
                    self.health_state = "OK"
                    self.health_logs = None
                    break

                except smtplib.SMTPHeloError:
                    self.health_state = "CRITICAL"
                    self.health_logs = (
                        "The SMTP server didn’t reply properly to the HELO greeting."
                    )
                    self.server = None

                except smtplib.SMTPAuthenticationError:
                    self.health_state = "CRITICAL"
                    self.health_logs = "The SMTP server didn’t accept the username/password combination."
                    self.server = None

                except smtplib.SMTPNotSupportedError:
                    self.health_state = "CRITICAL"
                    self.health_logs = (
                        "The SMTP server does not support the AUTH command."
                    )
                    self.server = None

                except smtplib.SMTPException:
                    self.health_state = "CRITICAL"
                    self.health_logs = "No suitable authentication method was found."
                    self.server = None

                except ConnectionError:
                    self.health_state = "CRITICAL"
                    self.health_logs = "The SMTP server could not be connected."
                    self.server = None

                except Exception as e:
                    self.health_state = "CRITICAL"
                    self.health_logs = "An exception occured: " + str(e)
                    self.server = None

                except:
                    self.health_state = "CRITICAL"
                    self.health_logs = "An exception occured."
                    self.server = None

        return self.health_state, self.health_logs

    def send_mail(self, receiver_email: str, sms: SMS) -> bool:
        """
        Deliver an SMS as E-mail.

        @param receiver_email: The recipient's e-mail address.
        @param sms: A SMS object to send as e-mail.
        @return: Returns True, if the E-mail was delivered to the Mail server and accepted. Returns False on error.
        """
        self.l.info(
            f"[{sms.get_id()}] Sending SMS as E-mail to recipient {receiver_email}."
        )
        try:
            msg = MIMEText(sms.to_string())

            msg["Subject"] = f"SMS from {sms.get_sender()} to {sms.get_recipient()}"
            msg["From"] = self.user
            msg["To"] = receiver_email

            if self.server is None:
                self._create_connection()

            self.l.info(
                f"[{sms.get_id()}] Try to send E-mail from {self.user} to {receiver_email}."
            )

            try:
                self.server.sendmail(self.user, receiver_email, msg.as_string())
            except UnicodeError as e:
                # if encoding is broken, try ascii
                self.l.info(
                    f"[{sms.get_id()}] Try to send text as ASCII instead of UTF-8."
                )
                self.server.sendmail(self.user, receiver_email, repr(msg.as_string()))

            self.l.info(f"[{sms.get_id()}] Sending E-mail was successful.")

            # A successful delivery clears the error state
            self.health_state = "OK"
            self.health_logs = None
            return True

        except smtplib.SMTPException as e:
            self.health_state = "CRITICAL"
            self.health_logs = "Failed to send E-mail: " + str(e)
            self.l.info(f"[{sms.get_id()}] Failed to send E-mail: " + str(e))
            self.server = None
            return False

        except Exception as e:
            self.health_state = "CRITICAL"
            self.health_logs = "Failed to send E-mail: " + str(e)
            self.l.warning(
                f"[{sms.get_id()}] Unknwon exception occured during SMTP delivery: "
                + str(e)
            )
            self.server = None
            return False

        except:
            self.health_state = "CRITICAL"
            self.health_logs = "Failed to send E-mail"
            self.l.warning(
                f"[{sms.get_id()}] Unknwon exception occured during SMTP delivery."
            )
            self.server = None
            return False
