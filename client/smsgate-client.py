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


import argparse
import xmlrpc.client, http.client
import ssl
import os
import sys
import time

def create_client(host, port, ca_file):
    context = ssl.create_default_context()
    context.load_verify_locations(ca_file)
    return xmlrpc.client.ServerProxy("https://%s:%d" % (host, port), context=context)
    
def send_ussd(host, port, ca_file, api_token, sender, ussd_code):

    s = create_client(host, port, ca_file)
    print("+ Sending USSD message and waiting for a response ...")
    result = s.send_ussd(api_token, sender, ussd_code)
    status = result[0]
    ussd_response = result[1]
    print("+ USSD response: %s" % ussd_response)

            

def send_sms(host, port, ca_file, api_token, sender, to, text):
    
    s = create_client(host, port, ca_file)
    print("+ Sending SMS and waiting for a response ...")
    uuid = s.send_sms(api_token, sender, to, text)

    while s.get_delivery_status(api_token, uuid) == False:
        print("  Waiting for delivery ...")
        time.sleep(3)
    print("+ SMS was delivered.")

def get_stats(host, port, ca_file, api_token):
    
    s = create_client(host, port, ca_file)
    print("+ Get status ...")
    result = s.get_stats(api_token)
    status = result[0]
    stats = result[1]

    print(f"{'#':4} {'Port':15} {'Phone number':15} {'dB':>4} {'Network':25} {'Balance':9} {'Snt':3} {'Rcv':3} {'#Init':5} {'Last init':16} {'Health':10} {'Health state message':25} {'Status':25}")

    for identifier in stats:
        i = stats[identifier]
        print(f"{identifier:4} {i['port']:15} {i['phone_number']:15} {i['current_signal']:>4} {i['current_network']:25} {i['currency']:3} {i['balance']:5} {i['sent']:3} {i['received']:3} {i['init_counter']:5} {i['last_init']:16} {i['health_state_short']:10} {i['health_state_message']:25} {i['status']:25}")


def input_phone_number(default):

    while True:
        
        phone_number_new = input("+ Phone number (Enter for last): ")
        if default != "" and phone_number_new == "":
            return default

        if phone_number_new != "":
            return phone_number_new

def shell(host, port, ca_file, api_token):

    get_stats(host, port, ca_file, api_token)

    command = None
    
    s = create_client(host, port, ca_file)

    # command loop
    phone_number = ""
    
    while command != 'exit':

        command = input("+ Command (ussd, sms, status, exit): ")

        if command == 'status' or command == '':
            get_stats(host, port, ca_file, api_token)
        elif command == 'ussd':
            phone_number = input_phone_number(phone_number)
            ussd_code = input("+ USSD code: ")
            send_ussd(host, port, ca_file, api_token, phone_number, ussd_code)
        elif command == 'sms':
            phone_number = input_phone_number(phone_number)
            destination = input("+ Destination: ")
            message = input("+ Message: ")            
            send_sms(host, port, ca_file, api_token, phone_number, destination, message)
    return 
    
        
def cmd_parser():
    
    parser = argparse.ArgumentParser(description='SMSGate client to interact with XMLRPC service.')
    
    parser.add_argument('--host', metavar='HOSTNAME', help='Hostname of the server API.', default="localhost")
    parser.add_argument('--port', metavar='PORT', type=int, help='Port number of the server API.', default=7000)
    parser.add_argument('--ca', metavar='CAFILE', help='The CA certificate file.')
    parser.add_argument('--api-token', metavar='TOKEN', help='The API token to use (prefer ENV variable SMSGATE_APITOKEN).')
    parser.add_argument('--sender', metavar='NUMBER', help='Use phone number to identify the modem, which should send the SMS/USSD.')

    subparsers = parser.add_subparsers()

    parser_a =  subparsers.add_parser('send-ussd', help='Send USSD code')    
    parser_a.add_argument('--code', metavar='CODE', help='The USSD code to send.', required=True)
    parser_a.set_defaults(ussd=True)

    parser_b =  subparsers.add_parser('send-sms', help='Send SMS')    
    parser_b.add_argument('--to', metavar='NUMBER', help='The recipient.', required=True)
    parser_b.add_argument('--text', metavar='TEXT', help='The text to send', required=True)
    parser_b.set_defaults(sms=True)
    
    parser_c =  subparsers.add_parser('stats', help='Retrieve status information from SMSGate')    
    parser_c.set_defaults(stats=True)

    parser_d =  subparsers.add_parser('shell', help='Start an interactive shell')    
    parser_d.set_defaults(shell=True)
    
    return parser.parse_args()

    
def main():
    
    args = cmd_parser()
    
    api_token = os.getenv("SMSGATE_APITOKEN", args.api_token)
    ca_file = args.ca if "ca" in args else None
    sender = args.sender
    
    try:
        if 'ussd' in args:
            return send_ussd(args.host, args.port, ca_file, api_token, sender, args.code)
    
        elif 'sms' in args:
            return send_sms(args.host, args.port, ca_file, api_token, sender, args.to, args.text)
        
        elif 'stats' in args:
            return get_stats(args.host, args.port, ca_file, api_token)

        elif 'shell' in args:
            return shell(args.host, args.port, ca_file, api_token)

    except ConnectionRefusedError:
        print(f"Failed to connect to {args.host}:{args.port}.")
        return
        
if __name__ == "__main__":
    sys.exit(main())
    
