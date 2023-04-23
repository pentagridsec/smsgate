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

import dbm
import logging
import os
import time
import threading
from typing import Optional


class SerialPortMapper:
    """
    Helper class to remember IMEI to serial port mappings.
    """

    class __SerialPortMapper:

        def __init__(self, serial_ports_hint_file: str):
            self.l = logging.getLogger(f"SerialPortMapper")
            self.serial_ports_hint_file = serial_ports_hint_file
            self.lock = threading.Lock()
            self.imei_to_port = {}
            self._load_hints()

            self.mappings_updated = threading.Event()
            self.background_task_thread = threading.Thread(target=self._background_task).start()

        def _background_task(self):
            while True:
                time.sleep(60)
                if self.mappings_updated.is_set():
                    self._store_hints()

        def _load_hints(self) -> None:
            self.l.debug(f"Load serial port mappings from {self.serial_ports_hint_file}.")
            with self.lock:
                if os.path.exists(self.serial_ports_hint_file):
                    with open(self.serial_ports_hint_file, 'r') as fh:
                        for l in fh.readlines():
                            splitted = l.rstrip().split(" ")
                            self.imei_to_port[splitted[0]] = splitted[1]

        def _store_hints(self) -> None:
            self.l.debug(f"Write serial port mappings to {self.serial_ports_hint_file}.")
            with self.lock:
                with open(self.serial_ports_hint_file, 'w') as fh:
                    self.mappings_updated.clear()
                    for imei, port in self.imei_to_port.items():
                        fh.write(f"{imei} {port}\n")

        def set_mapping(self, imei: str, device_name: str) -> None:
            self.l.debug(f"Add mapping from IMEI {imei} to serial port {device_name}.")
            self.imei_to_port[imei] = device_name
            self.mappings_updated.set()

        def get_mapping(self, imei: str) -> Optional[str]:
            self.l.debug(f"Try to find mapping for IMEI {imei}.")
            if imei in self.imei_to_port:
                port = self.imei_to_port[imei]
                self.l.debug(
                    f"Found mapping from IMEI {imei} to serial port {port} in cache."
                )
                return port
            else:
                self.l.debug(f"No mapping for IMEI {imei} in cache.")
                return None

        def _dump(self) -> None:
            for imei in self.imei_to_port:
                port = self.imei_to_port[imei]
                self.l.debug(f"IMEI {imei} -> serial port {port}")

    # instance variable
    instance = None

    def __init__(self, serial_ports_hint_file: str) -> None:
        if not SerialPortMapper.instance:
            SerialPortMapper.instance = SerialPortMapper.__SerialPortMapper(serial_ports_hint_file)

    def __getattr__(self, name):
        return getattr(self.instance, name)
