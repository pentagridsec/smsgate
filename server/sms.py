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

from __future__ import annotations

import datetime
import uuid
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from modem import Modem  # avoid circular dependency


class SMS:
    def __init__(
        self,
        sms_id: Optional[str],
        recipient: str,
        text: str,
        timestamp: Optional[datetime.datetime] = None,
        sender: Optional[str] = None,
        receiving_modem: Optional[Modem] = None,
        flash: bool = False,
    ) -> None:
        """
        This class represents an SMS.
        @param sms_id: Each SMS has an ID, which is technically a UUID.
        @param recipient: The recipient's phone number in international format as string.
        @param text: The SMS text as string.
        @param timestamp: A datetime representing the creation timestampt of this SMS.
        @param sender: The sender's phone number in international format as string. For received SMS, this is sometimes a human readable string with a name.
        @param receiving_modem: The receiving modem's identifier.
        @param flash: Send SMS as flash message, which should pop up on the destination phone and then disappear.
        """
        self.sms_id = sms_id if sms_id else str(uuid.uuid4())
        self.recipient = recipient
        self.text = text
        self.timestamp = timestamp if timestamp else datetime.datetime.now()
        self.created_timestamp = datetime.datetime.now()
        self.sender = sender
        self.receiving_modem = receiving_modem
        self.flash = flash

    def get_timestamp(self) -> datetime.datetime:
        """ Returns the timestamp as Python datetime. """
        return self.timestamp

    def get_age(self) -> datetime.timedelta:
        """ Returns the age as Python timedelta. """
        return datetime.datetime.now(datetime.timezone.utc) - self.timestamp

    def get_id(self) -> str:
        """ Returns the SMS ID, which is a UUID string. """
        return self.sms_id

    def get_text(self) -> str:
        """ Returns the SMS message test as string. """
        return self.text

    def get_recipient(self) -> str:
        """ Returns the recipient as string. """
        return self.recipient

    def get_sender(self) -> str:
        """ Returns the sender as string. """
        return self.sender

    def is_flash(self) -> bool:
        """ Returns status if the SMS is a flash SMS. """
        return self.flash

    def has_sender(self) -> bool:
        """
        Check if the object has a sender set.
        @return: Returns True or False.
        """
        return self.sender is not None and self.sender != ""

    def get_receiving_modem(self) -> Modem:
        """
        Get the modem that received the message.
        @return: Returns the receiving modem as Modem object.
        """
        return self.receiving_modem

    def to_string(self, content=True) -> str:
        """
        Format the whole message into a string.
        @return: Returns the entire SMS as formatted string.
        """
        ts_fmt = "%Y-%m-%d %H:%M:%S  %z"
        text = (
            f"SMS ID            : {self.sms_id}\n"
            + f"Sender            : {self.sender}\n"
            + f"Recipient         : {self.recipient}\n"
            + f"Message timestamp : {self.timestamp.strftime(ts_fmt)}\n"
            + f"Created timestamp : {self.created_timestamp.strftime(ts_fmt)}\n"
            + f"Flash message     : {self.flash}\n"
        )
        if self.receiving_modem:
            text += f"Receiving modem   : {self.receiving_modem.get_identifier()}\n"
            text += (
                f"Receiving network : {self.receiving_modem.get_current_network()}\n"
            )

        if content:
            text += (
                f"Text              :\n\n"
                + "---------------------------------------------------------\n"
                + self.text
                + "\n"
                + "---------------------------------------------------------\n"
            )

        return text
