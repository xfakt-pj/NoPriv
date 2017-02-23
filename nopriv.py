#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2013 Remy van Elst
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.

#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.

#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <http://www.gnu.org/licenses/>.

import imaplib
import email
import mailbox
from email.header import decode_header
from email.utils import parsedate
import time
import re
from math import ceil
from random import choice
import os
import base64
import cgi
import sys
import shutil
import errno
import datetime
import fileinput
import ConfigParser
from quopri import decodestring
import getpass

# places where the config could be located
config_file_paths = [ 
    './nopriv.ini',
    './.nopriv.ini',
    '~/.config/nopriv.ini',
    '/opt/local/etc/nopriv.ini',
    '/etc/nopriv.ini'
]

config = ConfigParser.RawConfigParser()
found = False
for conf_file in config_file_paths:
    if os.path.isfile(conf_file):
        config.read(conf_file)
        found = True
        break
if found == False:
    message = "No config file found. Expected places: %s" % \
        ("\n".join(config_file_paths), )
    raise Exception(message)


IMAPSERVER = config.get('nopriv', 'imap_server')
IMAPLOGIN = config.get('nopriv', 'imap_user')
IMAPPASSWORD = config.get('nopriv', 'imap_password')

if IMAPPASSWORD == "":
    IMAPPASSWORD = getpass.getpass()

IMAPFOLDER_ORIG = [ folder.strip() for folder in \
                     config.get('nopriv', 'imap_folder').split(',') \
                     if folder.strip() != "" ]

yes_flags = ['true', 1, '1', 'True', 'yes', 'y', 'on']

ssl = False
try: 
    ssl_value = config.get('nopriv', 'ssl')
    if ssl_value in yes_flags: 
        ssl = True
except:
    pass

incremental_backup = False
try:
    incremental_value = config.get('nopriv', 'incremental_backup')
    if incremental_value in yes_flags: 
        incremental_backup = True
except:
    pass

offline = False
try:
    offline_value = config.get('nopriv', 'offline')
    if offline_value in yes_flags: 
        offline = True
except:
    pass

enable_html = True
CreateMailDir = True
messages_per_overview_page = 50

inc_location = "inc"

def connectToImapMailbox(IMAPSERVER, IMAPLOGIN, IMAPPASSWORD):
    if ssl is True:
        mail = imaplib.IMAP4_SSL(IMAPSERVER)
    if ssl is False:
        mail = imaplib.IMAP4(IMAPSERVER)
    mail.login(IMAPLOGIN, IMAPPASSWORD)
    return mail

maildir = 'NoPrivMaildir'

def returnHeader(title, inclocation=inc_location):
    response = """
<!DOCTYPE html>
<html lang="en">
<head>
        <title>%s</title>
        <link rel="stylesheet" type="text/css" href="%s/css/bootstrap.css" media="all" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body>
    <div class="row">
        <div class="col-md-12">
    """ % (title, inclocation)
    return response

def returnFooter():
    response = """
                    </div>
                <div class="col-md-8 col-md-offset-1 footer">
                <hr />
                Email backup made by <a href="https://raymii.org/s/software/Nopriv.py.html">NoPriv.py from Raymii.org</a>
                </div>
            </body>
        </html>
    """
    return response

lastfolder = ""
def printQuote():
    quotes = ['Come on, shut off that damn alarm and I promise I\'ll never violate you again.', 'I\'ve become romantically involved with a hologram. If that\'s possible.', 'Listen to me very carefully because I\'m only going to say this once. Coffee - black.', 'Computer, prepare to eject the warp core - authorization Torres omega five nine three!', 'The procedure is quite simple. I\'ll drill an opening into your skull percisely two milimeters in diameter and then use a neuralyte probe to extract a sample of your parietal lobe weighing approximately one gram']
    return choice(quotes)

class DecodeError(Exception):
    pass

def decode_string(string):
    for charset in ("utf-8", 'latin-1', 'iso-8859-1', 'us-ascii', 'windows-1252','us-ascii'):
        try:
            return cgi.escape(unicode(string, charset)).encode('ascii', 'xmlcharrefreplace')
        except Exception:
            continue
    raise DecodeError("Could not decode string")

attCount = 0
lastAttName = ""
att_count = 0
last_att_filename = ""

def saveToMaildir(msg, mailFolder):
    global lastfolder
    global maildir

    mbox = mailbox.Maildir(maildir, factory=mailbox.MaildirMessage, create=True) 
    folder = mbox.add_folder(mailFolder)    
    folder.lock()
    try:
        message_key = folder.add(msg)
        folder.flush()

        maildir_message = folder.get_message(message_key)
        try:
            message_date_epoch = time.mktime(parsedate(decode_header(maildir_message.get("Date"))[0][0]))
        except TypeError as typeerror:
            message_date_epoch = time.mktime([2000, 1, 1, 1, 1, 1, 1, 1, 0])
        maildir_message.set_date(message_date_epoch)
        maildir_message.add_flag("s")


    finally:
        folder.unlock()
        folder.close()
        mbox.close()

def saveMostRecentMailID(mail_id, email_address, folder, filename = "nopriv.txt"):
    match = False
    for line in fileinput.input(filename, inplace = 1): 
        if line.split(":")[0] == folder and line.split(":")[1] == email_address and len(line) > 3:
            line = folder + ":" + email_address + ":" + str(mail_id)
            match = True
        if len(line) > 3 and line != "\n":
            print(line)
    fileinput.close()
    if match == False:
        with open(os.path.join(filename), 'a') as progress_file:
            progress_file.write(folder + ":" + email_address + ":" + str(mail_id))
            progress_file.close()    



def getLastMailID(folder, email_address, filename = "nopriv.txt"):
    if not os.path.exists(filename):
        with open(os.path.join(filename), 'w') as progress_file:
            progress_file.write(folder + ":" + email_address + ":1")
            progress_file.close()
    match = False
    with open(os.path.join(filename), 'r') as progress_file:
        for line in progress_file:
            if len(line) > 3:
                latest_mailid = line.split(":")[2]
                email_addres_from_file = line.split(":")[1]
                folder_name = line.split(":")[0]
                if folder_name == folder and email_addres_from_file == email_address:
                    progress_file.close()
                    return latest_mailid
        return 0
        progress_file.close()


def get_messages_to_local_maildir(mailFolder, mail, startid = 1):
    global IMAPLOGIN
    mail.select(mailFolder, readonly=True)
    try:
        typ, mdata = mail.search(None, "ALL")
    except Exception as imaperror:
        print("Error in IMAP Query: %s." % imaperror)
        print("Does the imap folder \"%s\" exists?" % mailFolder)
        return

    total_messages_in_mailbox = len(mdata[0].split())
    last_mail_id = 0
    try:
        last_mail_id = mdata[0].split()[-1]
    except Exception:
        pass
    folder_most_recent_id = getLastMailID(mailFolder, IMAPLOGIN)

    if folder_most_recent_id > 2 and incremental_backup == True:
        if not int(folder_most_recent_id) == 1:
            startid = int(folder_most_recent_id) + 1
    if startid == 0:
        startid = 1

    for message_id in range(int(startid), int(total_messages_in_mailbox + 1)):
        result, data = mail.fetch(message_id , "(RFC822)")
        raw_email = data[0][1]
        print('Saving message %s.' % (message_id))
        maildir_folder = mailFolder.replace("/", ".")
        saveToMaildir(raw_email, maildir_folder)
        if incremental_backup == True:
            saveMostRecentMailID(message_id, IMAPLOGIN, mailFolder)
        


def returnIndexPage():
    global IMAPFOLDER
    global IMAPLOGIN
    global IMAPSERVER
    global ssl
    global offline
    now = datetime.datetime.now()
    with open("index.html", "w") as indexFile:
        indexFile.write(returnHeader("Email Backup Overview Page"))
        indexFile.write("<div class=\"col-md-3 col-md-offset-1\">\n")
        indexFile.write("<h3>Folders</h3>\n")
        indexFile.write(returnMenu("", index=True, vertical = True, activeItem="index"))
        indexFile.write("</div>\n")
        indexFile.write("<div class=\"col-md-8\">\n")
        indexFile.write("<h3>Information</h3>\n")
        indexFile.write("<p>This is your email backup. You've made it with ")
        indexFile.write("<a href=\"https://raymii.org/s/software/Nopriv.py.html\"")
        indexFile.write(">NoPriv.py from Raymii.org</a>.<br />\n")
        indexFile.write("On the right you have the folders you wanted to backup.\n")
        indexFile.write("Click one to get the overview of that folder.<br />\n")
        indexFile.write("</p>\n<hr />\n<p>\n")
        indexFile.write("Here is the information you gave me: <br />\n")
        indexFile.write("IMAP Server: " + IMAPSERVER + "<br />\n")
        indexFile.write("Username: " + IMAPLOGIN + "<br />\n")
        indexFile.write("Date of backup: " + str(now) + "<br />\n")
        indexFile.write("Folders to backup: <br />\n<ul>\n")
        for folder in IMAPFOLDER:
            indexFile.write("\t<li><a href = \"" + folder + "/email-report-1.html\">" + folder + "</a></li>\n")
        indexFile.write("</ul>\n")
        indexFile.write("<br />Available Folders:<br />")
        if not offline:
            indexFile.write(returnImapFolders(available=True, selected=False, html=True))
        if ssl:
            indexFile.write("And, you've got a good mail provider, they support SSL and your backup was made over SSL.<br />\n")
        else:
            indexFile.write("No encrption was used when getting the emails.<br />\n")
        indexFile.write("Thats all folks, have a nice day!</p>\n")
        indexFile.write("</div>")
        indexFile.write(returnFooter())
        indexFile.close()


def allFolders(IMAPFOLDER_ORIG, mail):
    response = []
    if len(IMAPFOLDER_ORIG) == 1 and IMAPFOLDER_ORIG[0] == "NoPriv_All":
        maillist = mail.list()
        for imapFolder in sorted(maillist[1]):
            imapFolder = re.sub(r"(?i)\(.*\)", "", imapFolder, flags=re.DOTALL)
            imapFolder = re.sub(r"(?i)\".\"", "", imapFolder, flags=re.DOTALL)
            imapFolder = re.sub(r"(?i)\"", "", imapFolder, flags=re.DOTALL)
            imapFolder = imapFolder.strip()
            response.append(imapFolder)
    else:
        response = IMAPFOLDER_ORIG
    return response

def returnImapFolders(available=True, selected=True, html=False):
    response = ""
    if available:
        if not html:
            response += "Available IMAP4 folders:\n"
        maillist = mail.list()
        for ifo in sorted(maillist[1]):
            ifo = re.sub(r"(?i)\(.*\)", "", ifo, flags=re.DOTALL)
            ifo = re.sub(r"(?i)\".\"", "", ifo, flags=re.DOTALL)
            ifo = re.sub(r"(?i)\"", "", ifo, flags=re.DOTALL)
            if html:
                response += "- %s <br />\n" % ifo
            else:
                response += "- %s \n" % ifo
        response += "\n"

    if selected:
        if html:
            response += "Selected folders: <br />\n"
        else:
            response += "Selected folders:\n"
        for sfo in IMAPFOLDER:
            if html:
                response += "- %s <br />\n" % sfo
            else:
                response += "- %s \n" % sfo
    if html:    
        response += "<br />\n"
    else:
        response += "\n"

    return response


def returnMenu(folderImIn, inDate = False, index = False, vertical = False, activeItem = ""):
    global IMAPFOLDER

    folder_number = folderImIn.split('/')
    current_folder = folder_number
    folder_number = len(folder_number)
    dotdotslash = ""

    if vertical:
        response = '<ul class="nav nav-pills nav-stacked">'
    else:
        response = '<ul class="nav nav-pills">'

    if not index:
        for _ in range(int(folder_number)):
            dotdotslash += "../"
        if inDate:
            dotdotslash += "../../"
    if index:
        response += "\t<li class=\"active\"><a href=\"" + dotdotslash + "index.html\">Index</a></li>\n"
    else:
        response += "\t<li><a href=\"" + dotdotslash + "index.html\">Index</a></li>\n"


    for folder in IMAPFOLDER:
        if folder == activeItem:
            response += "\t<li class=\"active\"><a href=\"" + dotdotslash + folder + "/email-report-1.html\">" + folder + "</a></li>\n"
        else:
            response += "\t<li><a href=\"" + dotdotslash + folder + "/email-report-1.html\">" + folder + "</a></li>\n"

    if not index:
        response += "\t<li><a href=\"javascript:history.go(-1)\">Back</a></li>\n"
    else:
        response += "\t<li><a href=\"https://raymii.org\">Raymii.org</a></li>\n"
    response += "\n</ul>\n<hr />\n"

    return response

def remove(src):
    if os.path.exists(src):
        shutil.rmtree(src)

def copy(src, dst):
    try:
        shutil.copytree(src, dst)
    except OSError as exc:
        if exc.errno == errno.ENOTDIR:
            shutil.copy(src, dst)
        elif exc.errno == errno.EEXIST:
            print("File %s already exists." % src)
        else: raise

def move(src, dst):
        shutil.move(src, dst)

def moveMailDir(maildir):
    print("Adding timestamp to Maildir.")
    now = datetime.datetime.now()
    maildirfilename = "Maildir." + str(now).replace("/", ".").replace(" ", ".").replace("-", ".").replace(":", ".")
    move(maildir, maildirfilename)

def returnWelcome():
    print("##############################################")
    print("# NoPriv.py IMAP Email Backup by Raymii.org. #")
    if offline:
        print("# OFFLINE MODE ENABLED                       #")
    print("# version 6, released 17-11-2013.            #")
    print("# https://raymii.org - NoPriv.py is GPLv3    #")
    print("##############################################")
    print("")
    print("Runtime Information:")
    print(sys.version)
    print("")
    print(printQuote())
    print("")


def createOverviewPage(folder, pagenumber, amountOfItems = 50):
    if not os.path.exists(folder):
        os.makedirs(folder)
    overview_page_name = "email-report-" + str(pagenumber) + ".html"
    overview_file_path = os.path.join(folder, overview_page_name)
    with open(overview_file_path, "w") as overview_file:
        overview_file.write(returnHeader("Email backup page #" + str(pagenumber)))
        overview_file.write(returnMenu(folder, activeItem=folder))
        overview_file.write("<table class=\"table table-responsive table-striped\">")
        overview_file.write("<thead>")
        overview_file.write("<tr>")
        overview_file.write("<th>#</th>")
        overview_file.write("<th>From</th>")
        overview_file.write("<th>To</th>")
        overview_file.write("<th>Subject</th>")
        overview_file.write("<th>Date</th>")
        overview_file.write("</tr>")
        overview_file.write("</thead>")
        overview_file.write("<tbody>")
        overview_file.close()



def addMailToOverviewPage(folder, pagenumber, mail_id, mail_from, 
                          mail_to,  mail_subject, mail_date, 
                          mail_from_encoding = "utf-8", mail_to_encoding = "utf-8",
                          mail_subject_encoding = "utf-8", 
                          attachment = False, emptyFolder = False):
    try:
        mail_subject = cgi.escape(unicode(mail_subject, mail_subject_encoding)).encode('ascii', 'xmlcharrefreplace')
        mail_to = cgi.escape(unicode(mail_to, mail_to_encoding)).encode('ascii', 'xmlcharrefreplace')
        mail_from = cgi.escape(unicode(mail_from, mail_from_encoding)).encode('ascii', 'xmlcharrefreplace')
    except Exception:
        mail_subject = decode_string(mail_subject)
        mail_to = decode_string(mail_to)
        mail_from = decode_string(mail_from)

    try:
        email_date = str(time.strftime("%d-%m-%Y %H:%m", email.utils.parsedate(mail_date)))
        attachment_folder_date = str(time.strftime("%Y/%m/", email.utils.parsedate(mail_date)))
    except TypeError:
        email_date = "Error in Date"
        attachment_folder_date = str("2000/1/")

    email_file_path = os.path.join(attachment_folder_date, str(mail_id), "index.html")

    overview_page_name = "email-report-" + str(pagenumber) + ".html"
    overview_file_path = os.path.join(folder, overview_page_name)
    with open(overview_file_path, "a") as overview_file:
        overview_file.write("<tr>\n\t\t<td>")
        overview_file.write(str(mail_id))
        overview_file.write("</td>\n\t\t<td>")
        overview_file.write(mail_from.decode('string-escape'))
        overview_file.write("</td>\n\t\t<td>")
        overview_file.write(mail_to)
        overview_file.write("</td>\n\t\t<td>")
        if not emptyFolder:
            overview_file.write("<a href=\"" + email_file_path + "\">")
        overview_file.write(mail_subject)
        if not emptyFolder:
            overview_file.write("</a>")
        overview_file.write("</td>\n\t\t<td>")
        overview_file.write(str(mail_date))
        overview_file.write("</td>\n\t</tr>\n\t")
        overview_file.close()

def finishOverviewPage(folder, pagenumber, previouspage, nextpage, total_messages_in_folder):
    overview_page_name = "email-report-" + str(pagenumber) + ".html"
    overview_file_path = os.path.join(folder, overview_page_name)
    with open(overview_file_path, "a") as overview_file:
        overview_file.write("\t<tr>\n")
        overview_file.write("\t<td></td>\n")
        overview_file.write("\t\t<td>")
        if previouspage:
            overview_file.write("<a href = \"email-report-" + str(previouspage) + ".html\">Previous page (#" + str(previouspage) + ")</a>")
        else:
            overview_file.write("No previous page.")
        overview_file.write("</td>\n")

        overview_file.write("\t\t<td>")
        if nextpage:
            overview_file.write("<a href = \"email-report-" + str(nextpage) + ".html\">Next page (#" + str(nextpage) + ")</a>")
        else:
            overview_file.write("No more pages.")

        overview_file.write("</td>\n")
        overview_file.write("\t\t<td>")
        overview_file.write("Total items in folder: " + str(total_messages_in_folder))
        overview_file.write("</td>\n")

        overview_file.write("\t<td></td>\n")

        overview_file.write("\t</tr>")
        overview_file.write("\n</table>\n")
        overview_file.write(returnFooter())
        overview_file.close()



def createMailPage(folder, mail_id, mail_for_page, current_page_number,
                       mail_from, mail_to, mail_subject, mail_date,
                       mail_has_attachment = False,
                       mail_from_encoding = "utf-8", 
                       mail_to_encoding = "utf-8",
                       mail_subject_encoding = "utf-8"):

    mail = mail_for_page

    try:
        mail_subject = cgi.escape(unicode(mail_subject, mail_subject_encoding)).encode('ascii', 'xmlcharrefreplace')
        mail_to = cgi.escape(unicode(mail_to, mail_to_encoding)).encode('ascii', 'xmlcharrefreplace')
        mail_from = cgi.escape(unicode(mail_from, mail_from_encoding)).encode('ascii', 'xmlcharrefreplace')
    except Exception:
        mail_subject = decode_string(mail_subject)
        mail_to = decode_string(mail_to)
        mail_from = decode_string(mail_from)

    mail_number = int(mail_id)

    print(("Processing mail %s from %s with subject %s.") % ( mail_id, mail_from, mail_subject))

    try:
        email_date = str(time.strftime("%d-%m-%Y %H:%m", email.utils.parsedate(mail_date)))
        attachment_folder_date = str(time.strftime("%Y/%m/", email.utils.parsedate(mail_date)))
    except TypeError:
        email_date = "Error in Date"
        attachment_folder_date = str("2000/1/")

    content_of_mail = {}
    content_of_mail['text'] = ""
    content_of_mail['html'] = ""

    for part in mail.walk():
        part_content_type = part.get_content_type()
        part_charset = part.get_charsets()
        if part_content_type == 'text/plain':
            part_decoded_contents = part.get_payload(decode=True)
            try:
                if part_charset[0]:
                    content_of_mail['text'] += cgi.escape(unicode(str(part_decoded_contents), part_charset[0])).encode('ascii', 'xmlcharrefreplace')
                else:
                    content_of_mail['text'] += cgi.escape(str(part_decoded_contents)).encode('ascii', 'xmlcharrefreplace')
            except Exception:
                try:
                    content_of_mail['text'] +=  decode_string(part_decoded_contents)
                except DecodeError:
                    content_of_mail['text'] += "Error decoding mail contents."
                    print("Error decoding mail contents")
            continue
        elif part_content_type == 'text/html':
            part_decoded_contents = part.get_payload(decode=True)
            try:
                if part_charset[0]:
                    content_of_mail['html'] += unicode(str(part_decoded_contents), part_charset[0]).encode('ascii', 'xmlcharrefreplace')
                else:
                    content_of_mail['html'] += str(part_decoded_contents).encode('ascii', 'xmlcharrefreplace')
            except Exception:
                try:
                    content_of_mail['html'] += decode_string(part_decoded_contents)
                except DecodeError:
                    content_of_mail['html'] += "Error decoding mail contents."
                    print("Error decoding mail contents")

            continue



    has_attachments = mail_has_attachment
    folder_path_1 = os.path.join(folder, attachment_folder_date, str(mail_number))

    mail_html_page = os.path.join(folder_path_1, "index.html")
    with open(mail_html_page, 'w') as mail_page:
        mail_page.write(returnHeader(mail_subject + " - NoPriv.py Email Backup by Raymii.org", "../../../inc/"))
        mail_page.write(returnMenu(folder_path_1, activeItem=folder))
        mail_page.write("<table>\n")
        mail_page.write("\t<tr>\n")
        mail_page.write("\t\t<td>From: </td>\n")
        mail_page.write("\t\t<td>" + mail_from + "</td>\n")
        mail_page.write("\t<tr>\n")

        mail_page.write("\t<tr>\n")
        mail_page.write("\t\t<td>To: </td>\n")
        mail_page.write("\t\t<td>" + mail_to + "</td>\n")
        mail_page.write("\t<tr>\n")

        mail_page.write("\t<tr>\n")
        mail_page.write("\t\t<td>Subject: </td>\n")
        mail_page.write("\t\t<td>" + mail_subject + "</td>\n")
        mail_page.write("\t<tr>\n")

        mail_page.write("\t<tr>\n")
        mail_page.write("\t\t<td>Date: </td>\n")
        mail_page.write("\t\t<td>" + mail_date + "</td>\n")
        mail_page.write("\t<tr>\n")

        if has_attachments:
            mail_page.write("\t<tr>\n")
            mail_page.write("\t\t<td></td><td><a href=\"attachments\">Click here to open the attachments.</a> </td>\n")
            mail_page.write("\t<tr>\n")
        mail_page.write("\t<tr><td><br /></td>\n\t\t<td><a href=\"javascript:history.go(-1)\">Go back</a></td>\n\t</tr>\n")
        
        mail_page.write("</table>\n")

        if content_of_mail['text']:
            mail_page.write("<pre>")
            strip_header = re.sub(r"(?i)<html>.*?<head>.*?</head>.*?<body>", "", content_of_mail['text'], flags=re.DOTALL)
            strip_header = re.sub(r"(?i)</body>.*?</html>", "", strip_header, flags=re.DOTALL)
            strip_header = re.sub(r"(?i)<!DOCTYPE.*?>", "", strip_header, flags=re.DOTALL)
            strip_header = re.sub(r"(?i)POSITION: absolute;", "", strip_header, flags=re.DOTALL)
            strip_header = re.sub(r"(?i)TOP: .*?;", "", strip_header, flags=re.DOTALL)
            mail_page.write(decodestring(strip_header))
            mail_page.write("</pre>\n")
            

        if content_of_mail['html']:
            strip_header = re.sub(r"(?i)<html>.*?<head>.*?</head>.*?<body>", "", content_of_mail['html'], flags=re.DOTALL)
            strip_header = re.sub(r"(?i)</body>.*?</html>", "", strip_header, flags=re.DOTALL)
            strip_header = re.sub(r"(?i)<!DOCTYPE.*?>", "", strip_header, flags=re.DOTALL)
            strip_header = re.sub(r"(?i)POSITION: absolute;", "", strip_header, flags=re.DOTALL)
            strip_header = re.sub(r"(?i)TOP: .*?;", "", strip_header, flags=re.DOTALL)
            mail_page.write(decodestring(strip_header))
        
        mail_page.write("<a href=\"javascript:history.go(-1)\">Go back</a>")

        mail_page.close()        

def save_mail_attachments_to_folders(mail_id, mail, local_folder, folder):

    global att_count
    global last_att_filename
    returnTrue = False

    try:
        att_date = str(time.strftime("%Y/%m/", email.utils.parsedate(mail['Date'])))
    except TypeError:
        att_date = str("2000/1/")

    if not os.path.exists(os.path.join(folder, att_date, str(mail_id), "attachments/")):
        os.makedirs(os.path.join(folder, att_date, str(mail_id), "attachments/"))
    else:
        remove(os.path.join(folder, att_date, str(mail_id), "attachments/"))
        os.makedirs(os.path.join(folder, att_date, str(mail_id), "attachments/"))
 
    with open(os.path.join(folder, att_date, str(mail_id), "attachments/index.html"), "w") as att_index_file:
        att_index_file.write(returnHeader("Attachments for mail: " + str(mail_id) + ".", "../../../../inc"))
        att_index_file.write(returnMenu("../../../../../", activeItem=folder))
        att_index_file.write("<h1>Attachments for mail: " + str(mail_id) + "</h1>\n")
        att_index_file.write("<ul>\n")
        att_index_file.close()

    for part in mail.walk():
        if part.get_content_maintype() == 'multipart':
            continue
        if part.get('Content-Disposition') == None:
            continue
        decoded_filename = part.get_filename()
        filename_header = None
        try:
            filename_header = decode_header(part.get_filename())
        except (UnicodeEncodeError, UnicodeDecodeError):
            filename_header = None

        if filename_header:
            filename_header = filename_header[0][0]
            att_filename = re.sub(r'[^.a-zA-Z0-9 :;,\.\?]', "_", filename_header.replace(":", "").replace("/", "").replace("\\", ""))
        else:
            att_filename = re.sub(r'[^.a-zA-Z0-9 :;,\.\?]', "_", decoded_filename.replace(":", "").replace("/", "").replace("\\", ""))

        if last_att_filename == att_filename:
            att_filename = str(att_count) + "." + att_filename
        
        last_att_filename = att_filename
        att_count += 1
            

        att_path = os.path.join(folder, att_date, str(mail_id), "attachments", att_filename)
        att_dir = os.path.join(folder, att_date, str(mail_id), "attachments")

        att_locs = []
        with open(att_path, 'wb') as att_file:
            try:
                att_file.write(part.get_payload(decode=True))
            except Exception as e:
                att_file.write("Error writing attachment: " + str(e) + ".\n")
                print("Error writing attachment: " + str(e) + ".\n")
                return False
            att_file.close()

        with open(att_dir + "/index.html", "a") as att_dir_index:
            att_dir_index.write("<li><a href=\"" + str(att_filename) + "\">" + str(att_filename) + "</a></li>\n")
            att_dir_index.close()
            returnTrue = True
    
    with open(os.path.join(folder, att_date, str(mail_id), "attachments/index.html"), "a") as att_index_file:
        att_index_file.write("</ul>")
        att_index_file.write(returnFooter())
        att_index_file.close()
        if returnTrue:
            return True
        else:
            return False          

def extract_date(email):
    date = email.get('Date')
    return parsedate(date)

def return_sorted_email_list(maildir):
    sorted_mails = sorted(maildir, key=extract_date)
    sorted_mail_list = {}
    number = 0
    for mail in sorted_mails:
        sorted_mail_list[number] = mail
        number += 1

    return sorted_mail_list
    

def backup_mails_to_html_from_local_maildir(folder):
    global maildir
    global messages_per_overview_page
    ## Maildir folders have dots, not slashes
    local_maildir_folder = folder.replace("/", ".")
    local_maildir = mailbox.Maildir(os.path.join(maildir), factory=None, create=True)
    try:
        maildir_folder = local_maildir.get_folder(local_maildir_folder)
    except mailbox.NoSuchMailboxError as e:
        print(("Error: Folder \"%s\" is probably empty or does not exists: %s.") % (folder, e))
        createOverviewPage(folder, 1, 0)
        addMailToOverviewPage(folder, 1, 1, "-", "-", "Error: Folder/mailbox does not exist or is empty", "01-01-1900", emptyFolder = True)  
        finishOverviewPage(folder, 1, 0, 0, 0)
        return None

    ## Start with the first email
    mail_number = 1
    total_messages_in_folder = maildir_folder.__len__()
    try:
        number_of_overview_pages = float(total_messages_in_folder) / float(messages_per_overview_page)
        number_of_overview_pages = int(ceil(number_of_overview_pages))
    except Exception as error:
        print(error)
        raise
    
    sorted_maildir = return_sorted_email_list(maildir_folder)
    # We go through the mailbox in reverse
    start_mail_number = total_messages_in_folder

    ## Create the overview pages
    for number in reversed(range(number_of_overview_pages)):
        number += 1
        createOverviewPage(folder, number, messages_per_overview_page)
        
    current_page_number = 1

    ## Add the mail subject, from, to and date to the overview page
    run = 1
    for number in reversed(range(start_mail_number)):
        if (current_page_number * messages_per_overview_page) == mail_number:
            #if not current_page_number == 1:
            current_page_number += 1
        if not run == 1:
            mail_number += 1
        run += 1
        #key = maildir_folder.keys()[number]

        mail = sorted_maildir[number]
        mail_for_page = sorted_maildir[number]
        mail_subject = decode_header(mail.get('Subject'))[0][0]
        mail_subject_encoding = decode_header(mail.get('Subject'))[0][1]
        if not mail_subject_encoding:
            mail_subject_encoding = "utf-8"

        if not mail_subject:
            mail_subject = "(No Subject)"

        mail_from = email.utils.parseaddr(mail.get('From'))[1]

        mail_from_encoding = decode_header(mail.get('From'))[0][1]
        if not mail_from_encoding:
            mail_from_encoding = "utf-8"

        mail_to = email.utils.parseaddr(mail.get('To'))[1]
        mail_to_encoding = decode_header(mail.get('To'))[0][1]
        if not mail_to_encoding:
            mail_to_encoding = "utf-8"

        mail_date = decode_header(mail.get('Date'))[0][0]
        
        addMailToOverviewPage(folder, current_page_number, mail_number, 
                              mail_from, mail_to, mail_subject, mail_date, 
                              mail_from_encoding = mail_from_encoding, 
                              mail_to_encoding = mail_to_encoding,
                              mail_subject_encoding = mail_subject_encoding,
                            )  

        mail_has_attachment = save_mail_attachments_to_folders(mail_number, mail_for_page, folder, folder)

        createMailPage(folder, mail_number, mail_for_page, current_page_number,
                       mail_from, mail_to, mail_subject, mail_date, 
                       mail_has_attachment,
                       mail_from_encoding = mail_from_encoding, 
                       mail_to_encoding = mail_to_encoding,
                       mail_subject_encoding = mail_subject_encoding)
  

    ## Finish the overview page
    for number in reversed(range(number_of_overview_pages)):
        number += 1
        if number == 1 and number_of_overview_pages == 1:
            finishOverviewPage(folder, number, 0, 0, total_messages_in_folder)
        elif number == 1:
            finishOverviewPage(folder, number, 0, (number + 1), total_messages_in_folder)
        elif number == number_of_overview_pages:
            finishOverviewPage(folder, number, (number - 1), 0, total_messages_in_folder)
        else:
            finishOverviewPage(folder, number, (number - 1), (number + 1), total_messages_in_folder)    



returnWelcome()

if not offline:
    mail = connectToImapMailbox(IMAPSERVER, IMAPLOGIN, IMAPPASSWORD)
    IMAPFOLDER = allFolders(IMAPFOLDER_ORIG, mail)
    print(returnImapFolders())
    
returnIndexPage()

if not offline:
    for folder in IMAPFOLDER:    
        print(("Getting messages from server from folder: %s.") % folder)
        retries = 0
        if ssl:
            try:
                if folder:
                    get_messages_to_local_maildir(folder, mail)
            except imaplib.IMAP4_SSL.abort:
                if retries < 5:
                    print(("SSL Connection Abort. Trying again (#%i).") % retries)
                    retries += 1
                    mail = connectToImapMailbox(IMAPSERVER, IMAPLOGIN, IMAPPASSWORD)
                    get_messages_to_local_maildir(folder, mail)
                else:
                    print("SSL Connection gave more than 5 errors. Not trying again")
        else:
            try:
                if folder:
                    get_messages_to_local_maildir(folder, mail)
            except imaplib.IMAP4.abort:
                if retries < 5:
                    print(("Connection Abort. Trying again (#%i).") % retries)
                    retries += 1
                    mail = connectToImapMailbox(IMAPSERVER, IMAPLOGIN, IMAPPASSWORD)
                    get_messages_to_local_maildir(folder, mail)
                else:
                    print("Connection gave more than 5 errors. Not trying again")
                
        print(("Done with folder: %s.") % folder)
        print("\n")


for folder in IMAPFOLDER:
    print(("Processing folder: %s.") % folder)
    remove(folder + "/inc")
    copy(inc_location, folder + "/inc/")
    backup_mails_to_html_from_local_maildir(folder)
    print(("Done with folder: %s.") % folder)
    print("\n")    
        
if not incremental_backup:
    moveMailDir(maildir)
