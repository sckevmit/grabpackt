#!/usr/bin/env python

#######################################################################
#
#   grabpackt.py
#
#   Grab a free Packt Publishing book every day!
#
#   Author: Herman Slatman (https://hermanslatman.nl)
#
########################################################################
from __future__ import print_function

import requests
import argparse
import os
import sys
import smtplib
import zipfile
import codecs

from lxml import etree

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

try:
    # 3.x name
    import configparser
except ImportError:
    # 2.x name
    import ConfigParser as configparser

# relevant urls
LOGIN_URL = "https://www.packtpub.com/"
GRAB_URL = "https://www.packtpub.com/packt/offers/free-learning"
BOOKS_URL = "https://www.packtpub.com/account/my-ebooks"

# some identifiers / xpaths used
FORM_ID = "packt_user_login_form"
FORM_BUILD_ID_XPATH = "//*[@id='packt-user-login-form']//*[@name='form_build_id']"
CLAIM_BOOK_XPATH = "//*[@class='float-left free-ebook']"
BOOK_LIST_XPATH = "//*[@id='product-account-list']"

# specify UTF-8 parser; otherwise errors during parser
UTF8_PARSER = etree.HTMLParser(encoding="utf-8")

# create headers:
# user agent: Chrome 41.0.2228.0 (http://www.useragentstring.com/pages/Chrome/)
# Refererer: just set to not show up as some weirdo in their logs, I guess
HEADERS = {
    'User-Agent':
        'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/41.0.2228.0 Safari/537.36',
}

# the location for the temporary download location
BASE_DIRECTORY = os.path.dirname(os.path.realpath(__file__)) + os.sep
DOWNLOAD_DIRECTORY = BASE_DIRECTORY + 'tmp' + os.sep


# a minimal helper class for storing configuration keys and value
class Config(dict):
    pass


def configure():
    """Configures the script for execution."""
    # Argument parsing only takes care of a configuration file to be specified
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', help='specify a configuration file to be read', required=False)
    args = parser.parse_args()

    # Determine the configuration file to use
    configuration_file = os.path.join(BASE_DIRECTORY, args.config) if args.config else BASE_DIRECTORY + 'config.ini'

    # Check if the configuration file actually exists; exit if not.
    if not os.path.isfile(configuration_file):
        print('Please specify a configuration file or rename config.ini.dist to config.ini!')
        sys.exit(1)

    # Reading configuration information
    configuration = configparser.ConfigParser()
    configuration.read(configuration_file)

    # reading configuration variables
    config = Config()
    config.username = configuration.get('packt', 'user')
    config.password = configuration.get('packt', 'pass')
    config.download_enabled = configuration.getboolean('packt','download')
    config.download_types = configuration.get('packt', 'types')
    config.links_only = configuration.getboolean('packt', 'links_only')
    config.zip = configuration.getboolean('packt', 'zip')
    config.force_zip = configuration.getboolean('packt', 'force_zip')
    return config


def login(config, session):
    """Performs the login on the Pack Publishing website.

    Keyword arguments:
    config -- the configuration object
    session -- a requests.Session object
    """

    # static payload contains all static post data for login. form_id is NOT the CSRF
    static_login_payload = {
        'email': config.username, 'password': config.password, 'op': 'Login', 'form_id': FORM_ID
    }

    # get the random form build id (CSRF):
    req = session.get(LOGIN_URL)
    tree = etree.HTML(req.text, UTF8_PARSER)
    form_build_id = (tree.xpath(FORM_BUILD_ID_XPATH)[0]).values()[2]

    # put form_id in payload for logging in and authenticate...
    login_payload = static_login_payload
    login_payload['form_build_id'] = form_build_id

    # perform the login by doing the post...
    req = session.post(LOGIN_URL, data=login_payload)

    return req.status_code == 200


def relocate(session):
    """Navigates to the book grabbing url."""
    # when logged in, navigate to the free learning page...
    req = session.get(GRAB_URL)

    return req.status_code == 200, req.text


def get_owned_book_ids(session):
    """Returns a list of all owned books

    Keyword arguments:
    session -- a requests.Session object
    """
    # navigate to the owned books list
    my_books = session.get(BOOKS_URL)

    # get the element that contains the list of books and then all of its childeren
    book_list_element = etree.HTML(my_books.text, UTF8_PARSER).xpath(BOOK_LIST_XPATH)[0]
    book_elements = book_list_element.getchildren()

    # iterate all of the book elements, getting and converting the nid if it exists
    owned_book_ids = {int(book_element.get('nid')): book_element.get('title') for book_element in book_elements if book_element.get('nid')}
    print(owned_book_ids)

    return owned_book_ids


def get_book_id(contents):
    """Extracts a book id from HTML.

    Keyword arguments:
    contents -- a string containing the contents of an HTML page
    """
    # parsing the new tree
    free_learning_tree = etree.HTML(contents, UTF8_PARSER)

    # extract data: a href with ids
    claim_book_element = free_learning_tree.xpath(CLAIM_BOOK_XPATH)
    a_element = claim_book_element[0].getchildren()[0]
    # format: /freelearning-claim/{id1}/{id2}; id1 and id2 are numerical, length 5
    a_href = a_element.values()[0]

    # get the exact book_id
    claim_path = a_href[1:]
    book_id = claim_path.split('/')[1]

    return book_id, claim_path


def claim(session, claim_path):
    """Claims a book.

    Keyword arguments:
    session -- a requests.Session object
    claim_path -- the path to claim a book
    """
    # construct the url to claim the book; redirect will take place
    referer = GRAB_URL
    # format: https://www.packtpub.com/freelearning-claim/{id1}/{id2}
    claim_url = LOGIN_URL + claim_path
    session.headers.update({'referer': referer})
    req = session.get(claim_url)

    return req.status_code == 200, req.text


def prepare_links(config, book_element):
    """Prepares requested links.

    Keyword arguments:
    config -- the configuration object
    book_element -- an etree.Element describing a Packt Publishing book
    """

    # get the book id
    book_id = str(book_element.get('nid'))
    

    #BOOKS_DOWNLOAD_URL = "https://www.packtpub.com/ebook_download/" # + {id1}/(pdf|epub|mobi)
    #CODE_DOWNLOAD_URL = "https://www.packtpub.com/code_download/" # + {id1}
    # list of valid option links
    valid_option_links = {
        'p': ('pdf', '/ebook_download/' + book_id + '/pdf'),
        'e': ('epub', '/ebook_download/' + book_id + '/epub'),
        'm': ('mobi', '/ebook_download/' + book_id + '/mobi'),
        'c': ('code', '/code_download/' + str(int(book_id) + 1))
    }

    # get the available links for the book
    available_links = book_element.xpath('.//a/@href')

    # get the links that should be executed
    links = {}
    for option in list(str(config.download_types)):
        if option in list("pemc"):
            # perform the option, e.g. get the pdf, epub, mobi and/or code link
            dl_type, link = valid_option_links[option]

            # check if the link can actually be found on the page (it exists)
            if link in available_links:
                # each of the links has to be prefixed with the login_url
                links[dl_type] = LOGIN_URL + link[1:]
    print(links)
    return links


def download(session, book_id, links):
    """Downloads the requested file types for a given book id.

    Keyword arguments:
    session -- a requests.Session object
    book_id -- the identifier of the book
    links -- a dictionary of dl_type => URL type
    """
    if not os.path.exists(DOWNLOAD_DIRECTORY + "/" + book_id):
        os.makedirs(DOWNLOAD_DIRECTORY + "/" + book_id)
    files = {}
    for dl_type, link in links.items():
        filename = DOWNLOAD_DIRECTORY + book_id + '/'  + book_id + '.' + dl_type
        print(filename)

        # don't download files more than once if not necessary...
        if not os.path.exists(filename):
            req = session.get(link, stream=True)
            with open(filename, 'wb') as handler:
                for chunk in req.iter_content(chunk_size=1024):
                    if chunk: # filter out keep-alive new chunks
                        handler.write(chunk)
                        #f.flush()

        files[dl_type] = filename

    return files

def create_zip(files, book_name):
    """Zips up files.

    Keyword arguments:
    files -- a dictionary of dl_type => file name
    book_name -- the name of the book
    """
    zip_filename = DOWNLOAD_DIRECTORY + book_name + '.zip'
    zip_file = zipfile.ZipFile(zip_filename, 'w')
    for dl_type, filename in files.items():
        zip_file.write(filename, book_name + '.' + dl_type)

    zip_file.close()

    return zip_filename



def main():
    """Performs all of the logic."""

    # parsing the configuration
    config = configure()

    with requests.Session() as session:

        # set headers to something realistic; not Python requests...
        session.headers.update(HEADERS)

        # perform the login
        is_authenticated = login(config, session)

        if is_authenticated:

            # perform the relocation to the free grab page
            page_available, page_contents = relocate(session)

            # if the page is availbale (status code equaled 200), perform the rest of the process
            if page_available:

                # extract the new book id from the page contents
                new_book_id, claim_path = get_book_id(page_contents)

                # get a list of the IDs of all the books already owned
                owned_book_ids = get_owned_book_ids(session)
                has_claimed, claim_text = claim(session, claim_path)

                if config.download_enabled:
                    print("download_enabled")

                    # following is a redundant check; first verion of uniqueness;
                    # the book_id should be the nid of the first child of the list of books on the my-ebooks page
                    book_list_element = etree.HTML(claim_text, UTF8_PARSER).xpath(BOOK_LIST_XPATH)[0]

                    for boo in book_list_element.getchildren():
                        book_element = boo
                        book_id = boo.get('nid')
                        if book_id == None:
                            break

                        # extract the name of the book
                        book_title = book_element.get('title')

                        # get the links that should be downloaded and/or listed in mail
                        links = prepare_links(config, book_element)

                        # if we only want the links, we're basically ready for sending an email
                        # else we need some more juggling downloading the goodies
                        files = {}
                        zip_filename = ""
                        if not config.links_only:
                            # first download the files to a temporary location relative to grabpackt
                            print("Downloading book_id {}".format(book_id))
                            print("Downloading title {}".format(book_title))
                            files = download(session, book_id, links)

                            # next check if we need to zip the downloaded files
                            if config.zip:
                                # only pack files when there is more than 1, or has been enforced
                                if len(files) > 1 or config.force_zip:
                                    zip_filename = create_zip(files, book_title)

                                           

if __name__ == "__main__":
    main()
