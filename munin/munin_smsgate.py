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


import os
import xmlrpc.client, http.client
import ssl
import sys

def fetch():

    host = os.environ.get('smsgate_host', "localhost")
    port = int(os.environ.get('smsgate_port', "7000"))
    cafile = os.environ.get('smsgate_cafile')
    api_token = os.environ.get('smsgate_api_token')

    if api_token is None or api_token == "":
        print("Error: No API token found. Environment variable 'smsgate_api_token' not set?", file=sys.stderr)
        return None
    
    context = ssl.create_default_context()
    context.load_verify_locations(cafile)

    try:
        s = xmlrpc.client.ServerProxy("https://%s:%d" % (host, port), context=context)
        
        return s.get_stats(api_token)
    except ConnectionRefusedError:
        return None
    

def configure():

    #sent_warning = os.environ.get('smsgate_sent_warn', 10)
    #sent_critical = os.environ.get('smsgate_sent_crit', 100)

    #recv_warning = os.environ.get('smsgate_recv_warn', 10)
    #recv_critical = os.environ.get('smsgate_recv_crit', 100)

    #balance_warning = os.environ.get('smsgate_balance_warn', 5)
    #balance_critical = os.environ.get('smsgate_balance_crit', 10)


    data = fetch()
    if data is not None and data[0] == "OK":

        for identifier in data[1]:
        
            print(f"multigraph smsgate_sent_{identifier}")
            print(f"graph_title SMSGate - Sent via modem {identifier}")
            print("graph_args --base 1000 -l 0")
            print("graph_vlabel sent")
            print("graph_scale no")    
            print("graph_category smsgate")
        
            print(f"sent_{identifier}.label sent via {identifier}")
            print(f"sent_{identifier}.info SMS sent via modem {identifier}.")
            print(f"sent_{identifier}.type DERIVE")
            print(f"sent_{identifier}.min 0")

            print("")
        
        for identifier in data[1]:

            print(f"multigraph smsgate_recv_{identifier}")
            print(f"graph_title SMSGate - Received via modem {identifier}")
            print("graph_args --base 1000 -l 0")
            print("graph_vlabel received")
            print("graph_scale no")    
            print("graph_category smsgate")
        
            print(f"recv_{identifier}.label received via {identifier}")
            print(f"recv_{identifier}.info SMS received via modem {identifier}.")
            print(f"recv_{identifier}.type DERIVE")
            print(f"recv_{identifier}.min 0")

            print("")
            

        for identifier in data[1]:

            currency = data[1][identifier]['currency']
            
            print(f"multigraph smsgate_balance_{identifier}")
        
            print(f"graph_title SMSGate - Balance of SIM card in modem {identifier}")
            print("graph_args --base 1000 -l 0")
            print(f"graph_vlabel {currency}")
            print("graph_scale no")    
            print("graph_category smsgate")
        
            print(f"balance_{identifier}.label balance of {identifier}")
            print(f"balance_{identifier}.info Account balance of SIM card in modem {identifier}.")
            print(f"balance_{identifier}.type GAUGE")
            print(f"balance_{identifier}.min 0")
            #print(f"balance_{identifier}.warning {balance_warning}")
            #print(f"balance_{identifier}.critical {balance_critical}")
            print("")
            
    else:
        print("Error: Failed to connect to API.", file=sys.stderr)
    
def data():
    data = fetch()

    if data is not None and data[0] == "OK":

        for identifier in data[1]:

            print(f"multigraph smsgate_sent_{identifier}")
            print(f"sent_{identifier}.value {data[1][identifier]['sent']}")
            print("")
            
        for identifier in data[1]:
            print(f"multigraph smsgate_recv_{identifier}")
            print(f"recv_{identifier}.value {data[1][identifier]['received']}")
            print("")
            
        for identifier in data[1]:
            print(f"multigraph smsgate_balance_{identifier}")
            print(f"balance_{identifier}.value {data[1][identifier]['balance']}")
            print("")
            
    else:
        print("Error: Failed to connect to API.", file=sys.stderr)
            
def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "config":
        configure()
    else:
        data()
        
    
if __name__ == "__main__":
    main()
