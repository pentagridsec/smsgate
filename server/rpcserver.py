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
import itertools
from typing import Optional, Union, List, Tuple, Dict

from twisted.web import xmlrpc, server
from twisted.internet import reactor, endpoints, ssl
from OpenSSL import SSL

import helper
import sms
import logging
import configparser
import smtp
import modempool

# Our global variable for OpenSSL Cipher settings. It is read from the config
ciphers = ""
default_ciphers = "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:" \
                  "ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:" \
                  "DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:@STRENGTH"


class RPCServer(xmlrpc.XMLRPC):
    def __init__(
            self,
            config: configparser.ConfigParser,
            _modempool: modempool.ModemPool,
            smtp_delivery: smtp.SMTPDelivery,
    ) -> None:
        """
        Create a new XMLRPC server interface.
        This server interface is used to communicate with the SMS Gateway. It allows sending and retrieving SMS, sending
        USSD codes and retrieving answers, retrieving the health state, which includes the health state of
        sub-components such as the SMTPDelivery.
        @param config: A configuration object of type ConfigParser.
        @param _modempool: A ModemPool object to interact with.
        @param smtp_delivery: The SMTPDelivery object.
        """

        self.rlevel = "OK"
        self.rlogs = None

        self.l = logging.getLogger("RPCServer")

        self.config = config
        self.pool = _modempool
        self.smtp_delivery = smtp_delivery
        xmlrpc.XMLRPC.__init__(self)

        # read API token from configuration
        self.api_token = {}
        self.api_token["send_sms"] = config.get("api", "token_send_sms").split()
        self.api_token["send_ussd"] = config.get("api", "token_send_ussd").split()
        self.api_token["get_health_state"] = config.get(
            "api", "token_get_health_state"
        ).split()
        self.api_token["get_stats"] = config.get("api", "token_get_stats").split()

        self.api_token["get_sms"] = {}
        for modem_identifier in self.pool.get_identifier_for_phone_number():
            _key = f"token_{modem_identifier}_get_sms"
            try:
                _val = self.config.get("api", _key)
                self.api_token["get_sms"][modem_identifier] = _val.split()
            except configparser.NoOptionError:

                _msg = f"Warning: {_key} not defined in API key configuration."
                self.l.warning(_msg)
                self.rlogs = _msg
                self.rlevel = "WARNING"

    def _getPeerAddress(self) -> Optional[str]:
        """
        Get the peer's IP address.
        @return: Returns the peer's address as string.
        """
        return self.___request.getClientIP()

    def render(self, request):
        """
        Overwrite render() method from xmlrpc.XMLRPC to be able to intermediately store the XMLRPC request.
        @param request:
        @return:
        """
        self.___request = request
        return xmlrpc.XMLRPC.render(self, request)

    def xmlrpc_ping(self) -> str:
        """
        Exposed RPC function "ping" returns "OK" to check if this interface is reachable.
        @return: Returns the string "OK" to the caller.
        """
        return "OK"

    def xmlrpc_send_sms(
            self, token: str, sender: str, recipient: str, message: str
    ) -> str:
        """
        Exposed RPC function enqueues an SMS.

        Warning: Sending SMS may be used to commit fraud. It is possible to pay via SMS,
        and to book options, which could result in unwanted costs. To use this feature, SMS
        delivery must be enabled in the configuration file.

        To check the delivery status, call RPC function get_delivery_status().

        @param token: The API token to use.
        @param sender: The phone number, which identifies the SIM card to use. If it
        is an empty string, a SIM card is automatically selected.
        @param recipient: The recipients mobile number in E.123 international format.
        @param message: The text to send.
        @return: The function returns a string with the SMS ID in UUID format if the SMS was accepted.

        """

        if not self.config.getboolean("api", "enable_send_sms"):
            raise xmlrpc.Fault(405, "This API function is not enabled.")

        if not helper.check_token_in_list(token, self.api_token["send_sms"]):
            self.l.error(
                f"Invalid API token sent by client {self._getPeerAddress()}. API token was {token}."
            )
            raise xmlrpc.Fault(401, "Invalid API token.")

        recipient = helper.cleanup_phone_number(recipient)
        if not recipient:
            raise xmlrpc.Fault(400, "Invalid recipient format.")

        if sender != "":
            sender = helper.cleanup_phone_number(sender)
            if not sender:
                raise xmlrpc.Fault(400, "Invalid sender format.")

        new_sms = sms.SMS(sms_id=None, recipient=recipient, sender=sender, text=message)
        sms_id = self.pool.send_sms(new_sms)
        return sms_id

    def xmlrpc_get_delivery_status(self, token: str, sms_id: str) -> bool:
        """
        Exposed RPC function retrieves the delivery status of an SMS.
        @param token: The API token to use.
        @param sms_id: The SMS ID (a UUID) that the status is checked for.
        @return: The function returns a boolean value. True represents a delivered SMS and False indicates the SMS was
            not delivered (yet).
        """
        if not helper.check_token_in_list(token, self.api_token["send_sms"]):
            self.l.error(
                f"Invalid API token sent by client {self._getPeerAddress()}. API token was {token}."
            )
            raise xmlrpc.Fault(401, "Invalid API token.")

        self.l.info(f"Request delivery status for {sms_id}.")
        return self.pool.get_delivery_status(sms_id)

    def xmlrpc_get_sms(self, token: str, phone_number: str) -> List[sms.SMS]:
        """
        Exposed RPC function retrieves a list of SMS sent to a modem.
        @param token: The API token to use.
        @param phone_number:  Get SMS for this phone_number. If phone_number is empty,
            SMS to all phones are fetched if the API token permits this.
        @return: Returns a list of SMS objects or an empty list.
        """
        sms_list = []
        self.l.info('Fetch SMS for phone number "{phone_number}".')
        for modem_identifier in self.pool.get_identifier_for_phone_number(phone_number):

            if helper.check_token_in_list(
                    token, self.api_token["get_sms"][modem_identifier]
            ):
                sms_list += self.pool.get_buffered_sms(modem_identifier)
            else:
                self.l.error(
                    f"Invalid API token sent by client {self._getPeerAddress()}. API token was {token}."
                )
                raise xmlrpc.Fault(401, "Invalid API token.")

        return sms_list

    def xmlrpc_get_health_state(self, token: str) -> Tuple[str, str]:
        """
        Exposed RPC function retrieves the system's health state.
        Currently, this includes the modem pool's and the SMTP delivery module's health state.
        @param token: The API token to use.
        @return: The function returns a string tuple. The first element is either
            "OK", "WARNING" or "CRITICAL" and indicates the health state. The most severe level is reported. The
            second element is a string-concatenation of log messages or maybe an empty string if everything is okay.
        """
        if not helper.check_token_in_list(token, self.api_token["get_health_state"]):
            self.l.error(
                f"Invalid API token sent by client {self._getPeerAddress()}. API token was {token}."
            )
            raise xmlrpc.Fault(401, "Invalid API token.")

        plevel, plogs = self.pool.get_health_state()  # polls the cached state
        slevel, slogs = self.smtp_delivery.get_health_state()

        if slogs:
            slogs = slevel + ": " + slogs

        highest_level = helper.get_highest_warning_level([plevel, slevel, self.rlevel])
        combined_list = "; ".join(itertools.chain.from_iterable(filter(None, [plogs, slogs, self.rlogs])))

        return highest_level, combined_list

    def xmlrpc_send_ussd(self, token: str, sender: str, ussd_code: str) -> Tuple[str, str]:
        """
        Exposed RPC function sends USSD code via a modem identified via 'sender' and
        returns the decoded response.

        Warning: USSD code could be abused to change billing plans.
        Therefore, access should be restricted.

        @param token: The API token to use.
        @param sender: The sender's phone number in E.123 international
            format.
        @param ussd_code: The USSD code to send.
        @return: The function returns a two element list. The first element is
            either the string "OK" or "ERROR" indicating  the operation
            status. The second element is a string too. It is a USSD
            response when the status os "OK" and an error message when the
            status is "ERROR".
        """

        if not self.config.getboolean("api", "enable_send_ussd"):
            raise xmlrpc.Fault(405, "This API function is not enabled.")

        if not helper.check_token_in_list(token, self.api_token["send_ussd"]):
            self.l.error(
                f"Invalid API token sent by client {self._getPeerAddress()}. API token was {token}."
            )
            raise xmlrpc.Fault(401, "Invalid API token.")

        self.l.info(f"Sending USSD code {ussd_code} for {sender}.")
        modem_identifiers = self.pool.get_identifier_for_phone_number(sender)
        if modem_identifiers:
            ussd_response = self.pool.send_ussd(modem_identifiers[0], ussd_code)
            if ussd_response:
                self.l.info(f"USSD code sent. Response is: {ussd_response}")
                self.l.debug(helper.hexdump(ussd_response))
                return "OK", ussd_response
            else:
                msg = "Failed to send USSD code."
                self.l.error(msg)
                return "ERROR", msg
        else:
            msg = f"Modem could not be identified for phone number {sender}."
            self.l.error(msg)
            return "ERROR", msg

    def xmlrpc_get_stats(
            self, token: str
    ) -> Dict[str, Dict[str, Union[str, int, float]]]:
        """
        Exposed RPC function returns statistics.
        @param token: The API token to use.
        @return: See ModemPool.get_stats() for a description.
        """

        if not helper.check_token_in_list(token, self.api_token["get_stats"]):
            self.l.error(
                f"Invalid API token sent by client {self._getPeerAddress()}. API token was {token}."
            )
            raise xmlrpc.Fault(401, "Invalid API token.")

        return self.pool.get_stats()


class MySSLContext(SSL.Context):
    def __init__(self, method):
        SSL.Context.__init__(self, method)

        # default is to support tls 1.2, but anyway
        self.set_options(SSL.OP_NO_SSLv2)
        self.set_options(SSL.OP_NO_SSLv3)
        self.set_options(SSL.OP_NO_TLSv1)
        self.set_options(SSL.OP_NO_TLSv1_1)

        # For testing and debugging it may make sense to disable 1.2 or 1.3
        # self.set_options(SSL.OP_NO_TLSv1_2)
        # self.set_options(SSL.OP_NO_TLSv1_3)

        self.set_options(SSL.OP_CIPHER_SERVER_PREFERENCE)
        self.set_cipher_list(ciphers)


def set_up_server(
        config: configparser.ConfigParser,
        modempool: modempool.ModemPool,
        smtp: smtp.SMTPDelivery,
) -> None:
    """
    Create a new XMLRPC server.
    This server interface is used to communicate with the SMS Gateway. It allows sending and retrieving SMS, sending
    USSD codes and retrieving answers, retrieving the health state, which includes the health state of sub-components
    such as the SMTPDelivery.
    @param config: A configuration object of type ConfigParser.
    @param modempool: A ModemPool object to interact with.
    @param smtp: The SMTPDelivery object.
    """
    global ciphers

    port = config.getint("server", "port", fallback=7000)
    host = config.get("server", "host", fallback="localhost")
    cert = config.get("server", "certificate")
    key = config.get("server", "key")

    # read allowed ciphers, use a sane fallback value
    ciphers = config.get("server", "ciphers", fallback=default_ciphers)

    l = logging.getLogger("RPCServer")

    if config.getboolean("api", "enable_send_sms"):
        l.warning("Allowing others to send SMS means to allow others to book expensive options and to commit "
                  "fraud by sending messages to expensive service numbers.")

    sslContextFactory = ssl.DefaultOpenSSLContextFactory(
        key, cert, _contextFactory=MySSLContext
    )

    https_server = endpoints.SSL4ServerEndpoint(
        reactor, port, sslContextFactory=sslContextFactory, interface=host
    )

    l.debug("Launching site.")
    factory = server.Site(RPCServer(config, modempool, smtp))
    l.debug("Listen for connections.")
    https_server.listen(factory)
    l.debug("Calling run().")
    reactor.run(installSignalHandlers=False)
    l.info("RPCServer initialized.")
