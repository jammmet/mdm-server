import web, os, pprint, json, uuid, sys
from plistlib import *
from APNSWrapper import *
from creds import *
from datetime import datetime

#
# Simple, basic, bare-bones example test server
# Implements Apple's Mobile Device Management (MDM) protocol
# Compatible with iOS 4.x devices
# 
#
# David Schuetz, Senior Consultant, Intrepidus Group
#
# Copyright 2011, Intrepidus Group
# http://intrepidusgroup.com

#
# Revision History:
# 
# * August 2011 - initial release, Black Hat USA
# * January 2012 - minor tweaks, including favicon, useful README, and 
#   scripts to create certs, log file, etc.
#

LOGFILE = 'xactn.log'

###########################################################################
# Update this to match the UUID in the test provisioning profiles, in order 
#   to demonstrate removal of the profile

my_test_provisioning_uuid = 'REPLACE-ME-WITH-REAL-UUIDSTRING'

from web.wsgiserver import CherryPyWSGIServer
CherryPyWSGIServer.ssl_certificate = "Server.crt"
CherryPyWSGIServer.ssl_private_key = "Server.key"

###########################################################################

last_result = ''
last_sent = ''

global mdm_commands

urls = (
    '/', 'root',
    '/queue', 'queue_cmd',
    '/checkin', 'do_mdm',
    '/server', 'do_mdm',
    '/ServerURL', 'do_mdm',
    '/CheckInURL', 'do_mdm',
    '/enroll', 'enroll_profile',
    '/ca', 'mdm_ca',
    '/favicon.ico', 'favicon',
)



def setup_commands():
    global my_test_provisioning_uuid

    ret_list = dict()

    for cmd in ['DeviceLock', 'ProfileList', 'Restrictions',
        'CertificateList', 'InstalledApplicationList', 
        'ProvisioningProfileList',
	]:
        ret_list[cmd] = dict( Command = dict( RequestType = cmd ))

    ret_list['SecurityInfo'] = dict(
        Command = dict(
            RequestType = 'SecurityInfo',
            Queries = [
                'HardwareEncryptionCaps', 'PasscodePresent', 
                'PasscodeCompliant', 'PasscodeCompliantWithProfiles',
            ]
        )
    )

    ret_list['DeviceInformation'] = dict(
        Command = dict(
            RequestType = 'DeviceInformation',
            Queries = [
                'AvailableDeviceCapacity', 'BluetoothMAC', 'BuildVersion', 
                'CarrierSettingsVersion', 'CurrentCarrierNetwork', 
                'CurrentMCC', 'CurrentMNC', 'DataRoamingEnabled', 
                'DeviceCapacity', 'DeviceName', 'ICCID', 'IMEI', 'IsRoaming', 
                'Model', 'ModelName', 'ModemFirmwareVersion', 'OSVersion', 
                'PhoneNumber', 'Product', 'ProductName', 'SIMCarrierNetwork', 
                'SIMMCC', 'SIMMNC', 'SerialNumber', 'UDID', 'WiFiMAC', 'UDID',
                'UnlockToken',

    		'MEID', 'CellularTechnology', 'BatteryLevel', 
		    'SubscriberCarrierNetwork', 'VoiceRoamingEnabled', 
		    'SubscriberMCC', 'SubscriberMNC', 'DataRoaming', 'VoiceRomaing',
            'JailbreakDetected'
            ]
        )
    )

    ret_list['ClearPasscode'] = dict(
        Command = dict(
            RequestType = 'ClearPasscode',
            UnlockToken = Data(my_UnlockToken)
        )
    )

# commented out, and command string changed, to avoid accidentally
# erasing test devices.
#
#    ret_list['EraseDevice'] = dict(
#        Command = dict(
#            RequestType = 'DONT_EraseDevice',
#        )
#    )
#
    if 'Example.mobileconfig' in os.listdir('.'):
        my_test_cfg_profile = open('Example.mobileconfig', 'rb').read()
        pl = readPlistFromString(my_test_cfg_profile)

        ret_list['InstallProfile'] = dict(
            Command = dict(
                RequestType = 'InstallProfile', 
                Payload = Data(my_test_cfg_profile)
            )
        )

        ret_list['RemoveProfile'] = dict(
            Command = dict(
                RequestType = 'RemoveProfile',
                Identifier = pl['PayloadIdentifier']
            )
        )

    else:
        print "Can't find Example.mobileconfig in current directory."


    if 'MyApp.mobileprovision' in os.listdir('.'):
        my_test_prov_profile = open('MyApp.mobileprovision', 'rb').read()

        ret_list['InstallProvisioningProfile'] = dict(
            Command = dict(
                RequestType = 'InstallProvisioningProfile', 
                ProvisioningProfile = Data(my_test_prov_profile)
            )
        )

        ret_list['RemoveProvisioningProfile'] = dict(
            Command = dict(
                RequestType = 'RemoveProvisioningProfile',
        # need an ASN.1 parser to snarf the UUID out of the signed profile
                UUID = my_test_provisioning_uuid
            )
        )

    else:
        print "Can't find MyApp.mobileprovision in current directory."

    return ret_list


class root:
    def GET(self):
        return home_page()
        
class queue_cmd:
    def GET(self):
        global current_command, last_sent
        global my_DeviceToken, my_PushMagic
        i = web.input()
        cmd = i.command

        cmd_data = mdm_commands[cmd]
        cmd_data['CommandUUID'] = str(uuid.uuid4())
        current_command = cmd_data
        last_sent = pprint.pformat(current_command)

        wrapper = APNSNotificationWrapper('PushCert.pem', False)
        message = APNSNotification()
        message.token(my_DeviceToken)
        message.appendProperty(APNSProperty('mdm', my_PushMagic))
        wrapper.append(message)
        wrapper.notify()

        return home_page()



class do_mdm:        
    global last_result
    def PUT(self):
        global current_command, last_result
        HIGH='[1;31m'
        LOW='[0;32m'
        NORMAL='[0;30m'

        i = web.data()
        pl = readPlistFromString(i)
#        print i

        print "%sReceived %4d bytes: %s" % (HIGH, len(web.data()), NORMAL),

        if pl.get('Status') == 'Idle':
            print HIGH + "Idle Status" + NORMAL
            rd = current_command
            print "%sSent: %s%s" % (HIGH, rd['Command']['RequestType'], NORMAL)
#            print HIGH, rd, NORMAL

        elif pl.get('MessageType') == 'TokenUpdate':
            print HIGH+"Token Update"+NORMAL
            rd = do_TokenUpdate(pl)
            print HIGH+"Device Enrolled!"+NORMAL

        elif pl.get('Status') == 'Acknowledged':
            print HIGH+"Acknowledged"+NORMAL
            rd = dict()

        else:
            rd = dict()
            if pl.get('MessageType') == 'Authenticate':
                print HIGH+"Authenticate"+NORMAL
            else:
                print HIGH+"(other)"+NORMAL
                print HIGH, pl, NORMAL
        log_data(pl)
        log_data(rd)

        out = writePlistToString(rd)
#        print LOW, out, NORMAL

        q = pl.get('QueryResponses')
        if q:
            redact_list = ('UDID', 'BluetoothMAC', 'SerialNumber', 'WiFiMAC',
                'IMEI', 'ICCID', 'SerialNumber')
            for resp in redact_list:
                if q.get(resp):
                    pl['QueryResponses'][resp] = '--redacted--'
        for top in ('UDID', 'Token', 'PushMagic', 'UnlockToken'):
            if pl.get(top):
                pl[top] = '--redacted--'

        last_result = pprint.pformat(pl)
        return out


def home_page():
    global mdm_commands, last_result, last_sent, current_command

    drop_list = ''
    for key in sorted(mdm_commands.iterkeys()):
        if current_command['Command']['RequestType'] == key:
            selected = 'selected'
        else:
            selected = ''
        drop_list += '<option value="%s" %s>%s</option>\n'%(key,selected,key)

    out = """
<html><head><title>MDM Test Console</title></head><body>
<table border='0' width='100%%'><tr><td>
<form method="GET" action="/queue">
  <select name="command">
  <option value=''>Select command</option>
%s
  </select>
  <input type=submit value="Send"/>
</form></td>
<td align="center">Tap <a href='/enroll'>here</a> to <br/>enroll in MDM</td>
<td align="right">Tap <a href='/ca'>here</a> to install the <br/> CA Cert (for Server/Identity)</td>
</tr></table>
<hr/>
<b>Last command sent</b>
<pre>%s</pre>
<hr/>
<b>Last result</b> (<a href="/">Refresh</a>)
<pre>%s</pre>
</body></html>
""" % (drop_list, last_sent, last_result)

    return out


def do_TokenUpdate(pl):
    global my_PushMagic, my_DeviceToken, my_UnlockToken, mdm_commands

    my_PushMagic = pl['PushMagic']
    my_DeviceToken = pl['Token'].data
    my_UnlockToken = pl['UnlockToken'].data

    mdm_commands['ClearPasscode'] = dict(
        Command = dict(
            RequestType = 'ClearPasscode',
            UnlockToken = Data(my_UnlockToken)
        )
    )

    out = """
# these will be filled in by the server when a device enrolls

my_PushMagic = '%s'
my_DeviceToken = %s
my_UnlockToken = %s
""" % (my_PushMagic, repr(my_DeviceToken), repr(my_UnlockToken))

#    print out

    fd = open('creds.py', 'w')
    fd.write(out)
    fd.close()
    

    return dict()


class enroll_profile:
    def GET(self):

        if 'Enroll.mobileconfig' in os.listdir('.'):
            web.header('Content-Type', 'application/x-apple-aspen-config;charset=utf-8')
            web.header('Content-Disposition', 'attachment;filename="Enroll.mobileconfig"')
            return open('Enroll.mobileconfig', "rb").read()
        else:
            raise web.notfound()


class mdm_ca:
    def GET(self):

        if 'CA.crt' in os.listdir('.'):
            web.header('Content-Type', 'application/octet-stream;charset=utf-8')
            web.header('Content-Disposition', 'attachment;filename="CA.crt"')
            return open('CA.crt', "rb").read()
        else:
            raise web.notfound()


class favicon:
    def GET(self):

        if 'favicon.ico' in os.listdir('.'):
            web.header('Content-Type', 'image/x-icon;charset=utf-8')
#            web.header('Content-Disposition', 'attachment;filename="favicon.ico"')
            return open('favicon.ico', "rb").read()
        else:
            raise web.notfound()



mdm_commands = setup_commands()
current_command = mdm_commands['DeviceLock']


def log_data(out):
    fd = open(LOGFILE, "a")
    fd.write(datetime.now().ctime())
    fd.write(" %s\n" % repr(out))
    fd.close()

if __name__ == "__main__":
    print "Starting Server" 
    app = web.application(urls, globals())
    app.run()