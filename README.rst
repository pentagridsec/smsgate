`Pentagrid <https://www.pentagrid.ch/en/blog/open-source-sms-gateway-for-pentest-projects>`_'s ``SMSgate`` is a Python-based interface for sending and especially receiving SMS using multiple GSM modems and SIM cards.

.. contents:: 
   :local:

Short introduction
==================

``SMSgate`` is a multi-modem interface based on the Python module
`python-gsmmodem-new <https://github.com/babca/python-gsmmodem>`_, which is
used for receiving and sending SMS. The main use case for this SMS gateway
is receiving SMS and to forward the SMS or to allow XML-RPC clients to
fetch SMS via an API. The second use case is to send SMS alarms for
service monitoring purposes.

`Our blog post on the occasion of releasing the source code
<https://www.pentagrid.ch/en/blog/open-source-sms-gateway-for-pentest-projects>`_ gives
more background regarding this project.

Features
--------

The SMS gateway implements a few features which are:

- Support for a GSM modem pool attached via USB (or serial interfaces)
- Receive SMS and forward it via SMTP to a e-mail recipient
- XML-RPC API to fetch received SMS, to send SMS, to check the SMS delivery status, and to send USSD codes
- Support for API token to control API access
- Support for Icinga/Nagios monitoring
- Support for Munin monitoring
- An XML-RPC API client to interact with the service
- Experimental SECCOMP support (may break things)

The SMS gateway  misses these features:

- Persistence of SMS: Each SMS is kept in memory.
- User management: This is solved via API keys.
  
Supported hardware
-------------------

The Python module ``python-gsmmodem-new`` does not have a list of supported
devices, but this software should be usable with most modems. It has been tested with

* ZTE MF 190 (Surfstick)
* Quectel M35 modules (modem pool)
* SIM7600E modules (modem pool)
  
Installation
=============

Optional: Pass USB devices to KVM
-----------------------------------

If you want to operate the SMS gateway in a KVM guest system, you need to pass USB devices to the
guest. A problem is that if you have multiple devices with the same USB product and vendor ID, you
need to specify the device number, which changes every time you powercycle the modem(s). Alternativly,
you can pass an USB hub or use this script `this script <https://github.com/olavmrk/usb-libvirt-hotplug>`_, which
has `received a bug fix available <https://raw.githubusercontent.com/nitram2342/usb-libvirt-hotplug>`_.


Installation of the script:

1. Identify the main device path. Run:
::
    udevadm monitor --property --udev --subsystem-match=usb/usb_device

Be aware of modem pools bring their own USB hubs.
2. Download and install the code:
::

    wget https://raw.githubusercontent.com/nitram2342/usb-libvirt-hotplug/master/usb-libvirt-hotplug.sh
    sudo chown root.root usb-libvirt-hotplug.sh
    sudo mv usb-libvirt-hotplug.sh /usr/local/bin/
    sudo chmod 755 /usr/local/bin/usb-libvirt-hotplug.sh

3. Create ``/etc/udev/rules.d/90-usb-libvirt-hotplug.rules`` with the following content (adjust the DEVPATH and MYDOMAIN):
::

    SUBSYSTEM=="usb",DEVPATH=="/devices/pci0000:00/0000:00:14.0/usb1/1-11/1-11.1",OWNER="qemu",RUN+="/usr/local/bin/usb-libvirt-hotplug.sh MYDOMAIN"
    SUBSYSTEM=="usb",DEVPATH=="/devices/pci0000:00/0000:00:14.0/usb1/1-11/1-11.2",OWNER="qemu",RUN+="/usr/local/bin/usb-libvirt-hotplug.sh MYDOMAIN"

4. Check and maybe fix ownership:
::

    ls -l /etc/udev/rules.d/90-usb-libvirt-hotplug.rules
    chown root.root /etc/udev/rules.d/90-usb-libvirt-hotplug.rules
   
5. Reload Udev rules:
::

    sudo udevadm control --reload-rules


Create a user that runs the software and adjust Udev rules
-----------------------------------------------------------

Create a user that will later run the software:
::
    sudo useradd -d /var/smsgate -m -s /usr/sbin/nologin smsgate

Add user ``smsgate`` to group ``dialout``.
::

    sudo usermod -a -G dialout smsgate

Install dependencies
-----------------------

If you prefer to install as much Python packages via your OS package
manager as possible, run:

::

    sudo apt install python3-openssl python3-twisted python3-service-identity python3-venv python3-bcrypt
    python3 -m venv venv
    source venv/bin/activate
    pip3 install python-gsmmodem-new

Otherwise if you prefer your Python modules to have in a virtual
environment, run:

::

    sudo apt install python3-venv rustc librust-openssl-dev
    python3 -m venv venv
    source venv/bin/activate
    pip3 install -r requirements.txt
   
   
Install SMS gateway
--------------------

* Checkout code:
::

    git clone https://github.com/pentagridsec/smsgate

* Move code to installation directory:
::

    sudo mv smsgate /opt
    cd /opt/smsgate

* Create a directory to store runtime data
::

    mkdir /var/smsgate

* Fix permissions
::

    chown -R root.smsgate /opt/smsgate /var/cache/smsgate
    chmod 640 /opt/smsgate/*.conf
    chmod 644 /opt/smsgate/cert.pem
    chmod 770 /var/cache/smsgate

* Install service:
::

    cp smsgate.service /etc/systemd/system/
    sudo chown root.root /etc/systemd/system/smsgate.service

* Start service:
::

    sudo systemctl daemon-reload
    sudo systemctl enable smsgate
    sudo systemctl start smsgate
    sudo systemctl status smsgate
   

Configuration
==============


sim-cards.conf
--------------------

The ``sim-cards.conf`` configuration files contains the settings for the SIM
cards and corresponding modems. Each modem has an own SIM card and a
corresponding SIM card configuration entry. An example for a single modem
respectively SIM card is shown below.

::

    [00]
    enabled = True
    port=/dev/ttyUSB1
    phone_number = +491762xxxxxxx
    provider = Myprovider
    pin = 2342
    ussd_account_balance = *101#
    ussd_account_balance_regexp = Ihr Guthaben beträgt: ([\d+\,]+)
    currency = EUR
    account_balance_warning = 10.00
    account_balance_critical = 5.00
    prefixes = +49176 +49
    costs_per_sms = 0.09
    health_check_interval = 600
    imei = 35972xxxxxxxxxx
    encoding = UCS2
    #email_address = foo@example.com

The configuration is in the INI format. The modem is identified via a string.
Here it is ``00`` written in brackets. It refers to the modem slot ``00``,
but could be any other identifier as well. The ``enabled`` setting allows
the operator to disable a modem slot. If disabled, the modem is not initialized.
The ``port`` setting defines the serial interface, where the modem is attached.
If the exact port is not known, the file path may use wildcard such as ``/dev/ttyACM*``.
The SMS gateway will then probe for the device. It does so by looking for the ``imei``,
which is the International Mobile Equipment Identity and which identifies the modem.
The ``phone_number`` defines the phone number assigned to the SIM card. It is
used as identifier, for example for incoming SMS, but also to identify modems,
for example, when a user sends a USSD code or an SMS via the XMLRPC API. Then
it is possisble and for USSD codes necessary to specify a sender. The
``phone_number`` enables the gateway to find the right modem for sending the
SMS or the USSD code.

The ``provider`` is an
information about the operator, the SIM card is associated with. It is not
necessarily the same network operator the modem connects to. The information is not used
but it may be helpful to find SIM cards in the config file. The ``pin`` setting is
the SIM card PIN that unlocks secret keys on the SIM card to allow an
authentication towards the GSM network. If there is no SIM, leave it blank.

The ``ussd_account_balance`` is an USSD code to retrieve the account balance
associated with the SIM card. This is required for pre-paid accounts, which
require vouchers to be loaded to an account. When the USSD code is sent, the
network often returns a human-readable string. The ``ussd_account_balance_regexp``
is a regular expression, which is checked against the string returned by the
``ussd_account_balance`` operation in order to extract the account balance
value in a currency referred via ``currency``. If the account balance is
below a certain threshold, a warning respectively a fault is triggered
depending on the underrun of ``account_balance_warning`` or
``account_balance_critical``. If there is no ``ussd_account_balance`` or no
``ussd_account_balance_regexp`` setting, the balance is not checked. If
``account_balance_warning`` and ``account_balance_critical`` are set to
zero, neither a warning nor a critical is triggered, which effectively
disables the function.

The ``prefixes`` configuration value specifies which phone networks a modem
respectively a SIM card is responsible for. The setting's value is a list of
phone number prefixes in E.123 international format, which is used to feed
the SMS router. The standard router is a simple implementation with a
preference for low costs. Additionally, the list is also an allowed list.
If a prefix is not on the list, there is no route to the network. The
``costs_per_sms`` is the costs to send an SMS to a destination network. There
is not conversion between currencies. There is also only a fixed price per
SIM card. If the standard router does not fit, the model must be re-implemented.

The ``health_check_interval`` specified in seconds is used for the internal
monitoring. After this interval has expired, the server performs a modem, network
and account balance self check and updates internal flags.

The ``imei`` information is necessary to identify the modem, because USB
devices may be renumbered. To get the IMEI from your device, open a serial
connection

::
   
    picocom --echo -b 115200 /dev/ttyACM4
    AT+CGSN
    86053XXXXXXXXXX

smsgate.conf
--------------------

The ``smsgate.conf`` contains configurations for the SMS Gateway and its components.
An example configuration is shown below. The example is split into multiple sections
as described below.

::

    [mail]
    #enabled = True
    server = mymailserver.example.org
    port = 465
    user = myaccount@example.org
    password = secretpass
    recipient = mailbox@example.org
    health_check_interval = 600

A first section defines the SMTPS E-mail account for the SMTP delivery of received SMS. At the moment,
it is required to use SMTPS. The 'STARTTLS' mechanism is not supported. The ``recipient``
defines the destination E-mail address that receives incoming SMS. If E-mail forwarding
is not desired, the option can be disabled via the ``enabled`` setting by setting its
value to ``False``.

::

    [server]
    host = localhost
    port = 7000
    certificate = cert.pem
    key = key.pem

The next section defines the XMLRPC server interface that runs on ``host:port``. The server
supports TLS version >= 1.2. ``certificate`` and ``key`` refer to an X.509 certificate. When you
want to operate the gateway in the local network, binding the server to ``0.0.0.0`` is recommended.
otherwise it won't be accessible.

If you do not have an own certificate authority, generating and using a self-signed certificate is okay,
when you bind the client to also use this self-signed certificate as trust anchor. You can create a
private key and certificate by running:

::

    ./tools/make_cert.sh

This script creates a certificate with the CN set to ``localhost``. You may want to adjust this. Otherwise
clients trusting the self-signed certificate may fail at the hostname verification.
    
If you do not use a self-signed certificate, but a certificate deployed to your server, the path
can be entered there, for example:

::

    certificate = /etc/ssl/certs/myhostname.crt
    key = /etc/ssl/private/myhostname.key

You need to ensure the server can read the private key. If you use a Linux, your
certificates/keys may belong to the group ``ssl-cert``

::

    sudo usermod -a -G ssl-cert smsgate

In the next configuration section, the API access is configured.

::

    [api]

    # Allow users to send SMS via the XMLRPC API.
    # Warning: User may send SMS to expensive service lines.
    enable_send_sms = True

    # Allow users to send USSD codes via the XMLRPC API.
    # Warning: User may alter mobile billing plans and booking
    # options, which may lead to costs.
    enable_send_ussd = True

    # API token
    token_send_sms =   $2b$10$Vr3t8gYlc9.OFQspGP7Ez.fR9TLXnBVdZKZKgg77Vuspg16MOel4G
    token_send_ussd =  $2b$10$Vr3t8gYlc9.OFQspGP7Ez.fR9TLXnBVdZKZKgg77Vuspg16MOel4G
    token_get_health_state = $2b$10$yPqkNIyAZuzxLebb/oROiuoFxv2h9AlORWnMO312G8N9.oem0Xnpi
    token_get_stats =  $2b$10$yPqkNIyAZuzxLebb/oROiuoFxv2h9AlORWnMO312G8N9.oem0Xnpi
    token_00_get_sms = $2b$10$MIeCuGE9mZ0DiLv0RHZbweFtMHgEf/Wr20aNniYTvvullbGs9Rc7e
    token_01_get_sms = $2b$10$MIeCuGE9mZ0DiLv0RHZbweFtMHgEf/Wr20aNniYTvvullbGs9Rc7e
    token_02_get_sms = $2b$10$MIeCuGE9mZ0DiLv0RHZbweFtMHgEf/Wr20aNniYTvvullbGs9Rc7e

The setting ``enable_send_sms`` enables or disables access to the SMS
sending API. If sending SMS is not desired, this functionality can be disabled here. A
similar option is ``enable_send_ussd``, which gives control on enabling or disabling
sending USSD codes via the API.

When the XMLRPC API is used, the user must provide an access token. In the configuation
file, it is a bcrypt-hashed token. You can create API token with the ``tools/generate_api_token.py``
script like this:

::

    ./tools/generate_api_token.py
    Time             : 0.053636 s
    Hashed API Token : $2b$10$MIeCuGE9mZ0DiLv0RHZbweFtMHgEf/Wr20aNniYTvvullbGs9Rc7e
    API Token        : tymhoA1khwtcDIe3RD0DUoDiwH81BJ


Add its hash output to the configuration file and use the clear-text token on the
client side. You can add multiple hashed API token per config entry. They must be
separated with a space.

``token_send_sms`` is the API token required to send SMS and to fetch the SMS delivery state.
``token_send_ussd`` is quite the same for USSD codes, but without status fetching. There, the
API call returns the USSD response directly. The ``token_get_health_state`` API token is
intended for Icinga checks and the ``token_get_stats`` for a Munin plugin. In the
configuration file, there are several ``token_*_get_sms`` API token for retrieving SMS content
via individual modems. It allows you to assign modems to individuals for testing or to assign
a modem to a project group.

Warning: Please ensure that files containing API token have proper file permissions.
They likely won't with a standard ``umask`` value.

::

    [modempool]
    # Perform an internal health check after this time intervall in seconds.
    # The health check includes an account balance check. If the interval is
    # to tight, the balance check may fail.
    health_check_interval = 300

    # At a regular interval, each enabled modem sends an SMS to "itself".
    # This is part of the health check and generates a financial event
    # that may convince the operator to not shut down the subscription.
    # Possible values are: monthly, weekly, daily
    sms_self_test_interval = monthly

    # A file that stores previously found associations between serial ports
    # and IMEIs. These associations are used as hints on server (re)start to
    # speed-up the process. The file must be writable by the server user.
    serial_ports_hint_file = /var/cache/smsgate/serial_ports.hints

The ``modempool`` section contains settings to control the interval for
health checks. In addition, it is possible to trigger SMS sending at regular
intervals via the ``sms_self_test_interval`` setting. The ``serial_ports_hint_file``
setting controls where the service stores associations between IMEIs and
serial ports.

::

    [logging]
    # Log level: debug, info, warning, error, critical
    # Warning: Enabling DEBUG causes the SIM card pin and SMS to be logged.
    level = INFO

Furthermore, it is possible to define a log level via setting ``level`` on
which the SMS Gateway produces logs.

Last but not least, there is _experimental_ support for SECCOMP to restrict,
which system-calls are allowed to run. For non-allowed syscalls, the
kernel denies the operation. SECCOMP is disabled by default here, but it is possible to
enable this.

::

    [seccomp]
    # Experimental SECCOMP support. Enabling this may require startup debugging.
    enabled = False


Monitoring
===========

Icinga
-------

* Install plugin:

::

    cd /etc/icinga2/conf.d/
    ln -s /opt/smsgate/icinga/check_smsgate.py .
    ln -s /opt/smsgate/icinga/service-smsgate.conf .

* Ensure that Icinga is able to read the configuration files. Otherwise, the check will be silently
  ignored (but maybe logged somewhere).

* Restart icinga:

::

    systemctl restart icinga2
    systemctl status icinga2.service
   
Munin
----------

* To install ths Munin plugin, go to the Munin nodes plugin directory and add a link.

::

    cd /etc/munin/plugins
    ln -s /opt/smsgate/munin/munin_smsgate.py smsgate

* Edit ``/etc/munin/plugin-conf.d/munin-node``, add and adjust the following lines:

::

    [smsgate]
    env.smsgate_cafile /opt/smsgate/conf/cert.pem
    env.smsgate_host localhost
    env.smsgate_port 7000
    env.smsgate_api_token MY-API-KEY

Software Bill of Materials (SBOM)
==================================

A SBOM file in Cyclone-DX format has been added as ``cyclonedx-sbom.xml``.

Copyright and Licence
=====================

``SMSgate`` is developed by Martin Schobert <martin@pentagrid.ch> and
published under a BSD licence with a non-military clause. Please read
``LICENSE.txt`` for further details.

