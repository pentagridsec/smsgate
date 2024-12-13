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
import queue
import threading
import traceback
from typing import Optional, Union, List, Tuple, Dict

from modem import Modem
from sms import SMS
from smsrouter import SmsRouter


class ModemPool:
    """
    The ModemPool is responsible for managing the communication with
    modems and to pass data to and from individual modems.
    """

    def __init__(self, health_check_interval: int) -> None:
        """
        Create a modem pool.
        @param health_check_interval: Time in seconds after which an internal
        health check is performed.
        """
        self.modems = {}
        self.router = SmsRouter()

        # health states and lofs
        self.last_health_check = None
        self.health_check_interval = health_check_interval
        self.health_state = "OK"
        self.health_logs = None

        self.event_available = None  # used to signal events

        self.sms_queue_out = queue.Queue()
        self.sent_sms = {}  # a dict of sent SMS, value is an identifier (UUID)

        self.buffered_sms = {}  # key is a modem identifier, value a list of SMS objects

        # some statistics
        self.stats_sent = {}
        self.stats_received = {}

        self.l = logging.getLogger("ModemPool")

    def add_modem(self, modem: Modem) -> None:
        """
        Adds a modem to the modem pool.
        @param modem: A modem object that gets added to the pool.
        """
        identifier = modem.get_identifier()
        self.modems[identifier] = modem

        self.stats_sent[identifier] = 0
        self.stats_received[identifier] = 0

        if modem:
            self.router.add(identifier, modem.get_prefixes(), modem.get_costs(), modem)

    def set_event_thread(self, event_available: threading.Event) -> None:
        """
        Pass a threading.Event object to ModemPool object to be able to notify about incoming andoutgoing SMS.
        @param event_available: A threading.Event object to signal between threads. For an incoming or outgoing SMS, the
            event object's method set() is called.
        """
        self.event_available = event_available

    def get_health_state(self) -> Tuple[str, Optional[str]]:
        """
        Get the health state.
        @return: Returns the modem's internal health state as tuple of State, Message. State is either "OK", "WARNING",
            or "CRITICAL". Message is a human-readable string giving details about the issue. Message may be a None.
        """
        return self.health_state, self.health_logs

    def do_health_check(self) -> Tuple[str, Optional[str]]:
        """
        Internal method that potentially triggers a health check.
        This method checks if performing a health check is necessary and will act accordingly.
        @return: Returns the modem's internal health state as tuple of State, Message. State is either "OK", "WARNING",
            or "CRITICAL". Message is a human-readable string giving details about the issue. Message may be a None.
        """
        now = datetime.datetime.now()
        if (
            (self.last_health_check is None)
            or (self.health_state != "OK")
            or (
                (now - self.last_health_check).total_seconds()
                >= self.health_check_interval
            )
        ):

            self.last_health_check = now

            max_level = "OK"
            logs = []

            if len(self.modems) == 0:
                max_level = "CRITICAL"
                logs.append(f"There are no modems in the modem pool.")

            self.l.info("Collecting health check infos from modems")

            for identifier, modem in self.modems.items():
                # collect single health state
                if modem:
                    state, log = modem.get_health_state()
                    self.l.debug(f"Modem [{identifier}] reported: {state}, {log}.")
                else:
                    state = "WARNING"  # If there is no modem object, it is disabled on purpose.
                    log = f"[{identifier}] Modem object is not initialized."

                # decide of max_level changes
                if state != "OK":
                    logs.append(f"{state}: " + log)

                    if state == "WARNING":
                        if max_level == "OK":
                            max_level = state

                    elif state == "CRITICAL":
                        max_level = state

            self.health_state = max_level
            self.health_logs = ";".join(logs) if logs else None

            # Even if not part of the health check, we check if
            # there are internal structures to clean up
            self._cleanup()

        return self.health_state, self.health_logs

    def get_identifier_for_phone_number(
        self, phone_number: Optional[str] = None
    ) -> List[str]:
        """
        Retrieve modem identifier for the modem that matches a given phone number.
        Otherwise, return all modem identifier.
        @param phone_number: A phonenumber to look up or None
        @return: Returns a list of modem identifiers (basically a string label). The returned list is empty, if a
            matching modem was not found.
        """
        if phone_number == "" or phone_number is None:
            return self.modems.keys()
        else:

            matching_identifier = []

            for identifier in self.modems:
                modem = self.modems[identifier]
                if modem.get_phone_number() == phone_number:
                    matching_identifier.append(identifier)

            return matching_identifier

    def send_sms(self, sms: SMS) -> str:
        """
        Send an SMS by putting it into the sending queue.
        If the SMS object has a sender defined, this sender will also define the sending modem. If the sending modem is
            not available, the decision on which sender to use is handed over to the SmsRouter.
        If the SMS object has no sender defined, the ModemPool will use the SmsRouter to decide via which modem the SMS
            will be sent.
        You need to call process_outgoing_sms() to really send SMS.
        @param sms: An SMS object, which contains the destination number and the message text.
        @return: Returns the SMS ID (a UUID) as string. You may use this information to later check the delivery status.
        """
        self.sms_queue_out.put(sms)
        self.event_available.set()
        return sms.get_id()

    def send_ussd(self, modem_identifier: str, ussd_code: str) -> str:
        """
        Send a USSD code via a modem. The function should not be called frequently, because it is not
        executed in a separate thread.
        @param modem_identifier: The modem identifier (basically a string label from the config file) for the modem that
            should send the USSD message.
        @param ussd_code: A string specifying what should be sent, for example "*100#".
        @return: Returns a string with the networks response to the USSD code.
        """
        return self.modems[modem_identifier].send_ussd(ussd_code)

    def process_outgoing_sms(self) -> None:
        """
        Flush the outgoing SMS queue.
        This method should be called from outside the class to process outgoing SMS that have been put into the internal
        sending queue before. The method checks how to route each SMS in the queue and the SMS is then handed over
        to the modem for delivery. Handing over the SMS does not take that much time, therefore, it seems not necessary
        to do this in an own thread.
        """
        while not self.sms_queue_out.empty():

            self.l.info(
                f"[{threading.get_ident()}] There are SMS to deliver to other phones."
            )
            sms = self.sms_queue_out.get()

            identifier = None

            if sms.has_sender():
                identifier_list = self.get_identifier_for_phone_number(sms.get_sender())
                if identifier_list is not None and len(identifier_list) > 0:
                    identifier = identifier_list[0]
                else:
                    self.l.warning(f"An SMS should be sent, a sender is specified as {sms.get_sender()}, but it was "
                                   "not possible to find a matching modem/SIM card. Fallback to let the router "
                                   "decide which modem to use.")

            # check health state
            if identifier:
                state, log = self.modems[identifier].get_health_state()
                if state != "OK":
                    self.l.warning(f"An SMS should be sent, a sender is specified as {sms.get_sender()}, but the modem "
                                   "seems to have a problem. Fallback to let the router decide which modem to use.")
                    identifier = None

            if identifier is None:
                identifier = self.router.get(sms.get_recipient())

            if identifier:
                self.l.info(
                    f"Will deliver SMS {sms.get_id()} to {sms.get_recipient()} via modem {identifier}."
                )

                # put SMS in a modem's queue
                self.modems[identifier].send_sms(sms)

                # remember where the SMS was sent.
                self.sent_sms[sms.get_id()] = identifier

                # add to stats
                self.stats_sent[identifier] += 1

            else:
                self.l.error(f"Failed to find a way to deliver SMS {sms.get_id()}. The SMS is removed from the "
                             "queue and won't be put back.")

        # check if there are internal structures to clean up
        self._cleanup()

    def get_delivery_status(self, sms_id: str) -> bool:
        """
        Check for an SMS ID if the SMS was sent.
        The functions looks up which modem sent the SMS and forwards the
        "request" to the modem object.
        @param sms_id: The SMS' UUID as string.
        @return: The function returns either True or False.
        """
        if sms_id in self.sent_sms:
            identifier = self.sent_sms[sms_id]
            return self.modems[identifier].get_delivery_status(sms_id)

        return False

    def _cleanup(self) -> None:
        """
        Clean up internal tables.
        """
        self.l.info("Clean up modempool internal structures.")

        self.l.debug("Clean up for sent SMS.")
        _tmp = []
        for sms_id in self.sent_sms:
            identifier = self.sent_sms[sms_id]
            if self.modems[identifier].cleanup(sms_id):
                _tmp.append(sms_id)

        for i in _tmp:
            del self.sent_sms[i]

        self.l.debug("Clean up internal modempool data structures.")

        try:

            _tmp = []
            for identifier in self.buffered_sms:
                self.l.debug(
                    f"Clean up internal modempool data structures for {identifier}."
                )

                for sms_id, _sms in self.buffered_sms[identifier].items():

                    if _sms.get_age().total_seconds() > 60:  # todo increase value
                        self.l.debug(f"Delete entry for {sms_id}.")
                        _tmp.append((identifier, sms_id))

            for identifier, sms_id in _tmp:
                del self.buffered_sms[identifier][sms_id]

        except Exception as e:
            self.l.error("Exception: " + str(e), exc_info=1)
            self.l.error(traceback.format_exc(), exc_info=1)

        self.l.debug("Clean up completed.")

    def get_buffered_sms(self, identifier: str) -> List[SMS]:
        """
        Retrieve a buffered SMS.
        Incoming SMS are usually forwarded by e-mail if this is configured, but it is still necessary to keep it for the
            XMLRPC  interface. Therefore, incoming SMS are buffered for some time.
        @param identifier: The modem identifier as string.
        @return: Returns a list of buffered SMS objects. An empty list is returned if there are no SMS objects.
        """
        return self.buffered_sms[identifier]

    def _buffer_sms(self, identifier: str, _sms: SMS) -> None:
        """
        Buffer an incoming SMS for later retrivial via the XMLRPC API.
        @param identifier: The identifier for the modem that received the SMS.
        @param _sms: The SMS object.
        """
        if identifier not in self.buffered_sms:
            self.buffered_sms[identifier] = {}

        self.buffered_sms[identifier][_sms.get_id()] = _sms

    def get_incoming_sms(self) -> Optional[SMS]:
        """
        Check if a Modem object has an SMS and return it.
        Usually the Modem signals incoming SMS and the signalled code uses this function to get the SMS object. The SMS
            is removed from the queue. The calling code may put it back into the queue via send_sms().
        @return: If there is an SMS, the SMS is returned, otherwise None.
        """
        for identifier in self.modems:
            modem = self.modems[identifier]

            self.l.debug(f"Check if modem {identifier} has an SMS.")
            if modem and modem.has_sms():
                self.l.debug(f"Modem {identifier} has an SMS.")
                try:
                    sms = modem.get_sms()
                    if sms:
                        self._buffer_sms(identifier, sms)

                        # add to stats
                        self.stats_received[identifier] += 1
                        self.l.debug(f"New SMS found for modem {identifier}.")
                        return sms

                except queue.Empty:
                    self.l.debug(
                        f"Modem {identifier} should have an SMS, but it couln't be fetched.."
                    )
                    pass

        self.l.info(f"No new SMS found.")
        return None

    def get_stats(self) -> Dict[str, Dict[str, Union[str, int, float]]]:
        """
        Return collected statistics and status information.
        @return: Returns data as dictionary structure. The outer dictionary has the form key -> value, where key is a
            modem identifier and value is an inner dict. The inner dict also has key, value properties, where key and is
            a string and value either a string, float or int.
        """

        def _none_to_str(v):
            return v if v is not None else ""

        stats = {}
        for identifier in self.modems:

            m = self.modems[identifier]

            if m:
                stats[identifier] = {}
                stats[identifier]["phone_number"] = m.get_phone_number()

                stats[identifier]["current_network"] = _none_to_str(
                    m.get_current_network()
                )
                stats[identifier]["current_signal"] = m.get_current_signal_dB()
                stats[identifier]["port"] = _none_to_str(m.get_port())
                stats[identifier]["status"] = _none_to_str(m.get_status())

                stats[identifier]["balance"] = _none_to_str(m.get_balance())
                stats[identifier]["currency"] = _none_to_str(m.get_currency())

                stats[identifier]["sent"] = _none_to_str(self.stats_sent[identifier])
                stats[identifier]["received"] = _none_to_str(
                    self.stats_received[identifier]
                )

                health = m.get_health_state()
                stats[identifier]["health_state_short"] = _none_to_str(health[0])
                stats[identifier]["health_state_message"] = _none_to_str(health[1])
                stats[identifier]["init_counter"] = m.get_init_counter()

                fmts = "%Y-%m-%d %H:%M"
                stats[identifier]["last_init"] = m.get_last_init().strftime(fmts)
                stats[identifier]["last_received"] = m.get_last_received().strftime(fmts) if m.get_last_received() else ""
                stats[identifier]["last_sent"] = m.get_last_sent().strftime(fmts) if m.get_last_sent() else ""

        self.l.info(stats)
        return stats
