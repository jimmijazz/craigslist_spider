# Scrapes property rental listings from craigslist.org

##### ASSUMPTIONS #####

# - Pets are not allowed unless explicitly stated
# - No laundry in building unless stated
# - Smoking is allowed unless stated
# - Rent is listed as per/week  (No indication otherwise)

import scrapy, csv, json, requests, pydispatch, smtplib

# Email modules
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Web scraping modules
from scrapy.selector import Selector
from scrapy.http import HtmlResponse
from scrapy import signals
from scrapy.xlib.pydispatch import dispatcher
from scrapy.exporters import JsonItemExporter

# HTML parser
from bs4 import BeautifulSoup as bs4

# SPIDER SETTINGS
TESTING = False                      # True = First listing on first indexed page
EMAIL = "joshua.bitossi@gmail.com"  # Where to send an email when finished
SPIDER_NAME = "craigslist"          # Scrapy Spider name
DOWNLOAD_DELAY = 0.2                # Delay (in seconds) between requests
AUTOTHROTTLE = True                 # Limits requests See: http://bit.ly/2gskbXi
ALLOWED_DOMAINS = ['craigslist.org']

# URLS TO CRAWL
START_URLS = {
            "boston"    :     'https://boston.craigslist.org',
            "new_york"  :     'https://newyork.craigslist.org'
            }

property_data = {}      # Dictionary of properties {ID:attributes}

current_url = ""        # Used to store the base url across functions.

class CraigListSpider(scrapy.Spider):

    name= SPIDER_NAME
    setings = {
        'DOWNLOAD_DELAY'       : DOWNLOAD_DELAY,
        'AUTOTHROTTLE_ENABLED' : AUTOTHROTTLE,
        'ROBOTSTXT_OBEY'       : False,
        'FEED_URI'             : './properties.txt',
        'FEED_FORMAT'          : 'json',
    }

    def __init__(self):
        dispatcher.connect(self.spider_closed, signals.spider_closed)

    def start_requests(self):
        """ Makes initial request external server, forwards to self.parse
            function. Required by Scrapy.
            start_requests(self, string) -> None
        """

        index_urls = []

        # Index pages to scrap from initial URLS given
        for key, value in START_URLS.items():
            try:
                global current_url    # Get base URL
                current_url = value   # Set starting URL
                # Get all listing/results pages
                index_urls = self.indexPages(current_url + "/search/aap?s=100" )
            except Exception as e:
                print (e)

        # For each index page, scrape URLS
        for url in index_urls:
            try:
                yield scrapy.Request(url=url, callback=self.parse)
                if TESTING == True:
                    break
            except Exception as e:
                print (e)

    def indexPages(self, start_page):
        """ Creates a list of all URLS for the spider to index.

            indexPages(string) -> list[string]
        """

        urls = []

        response = requests.get(start_page)
        page = bs4(response.content, "lxml")

        last = False    # Is it the last page
        while last == False:
            last = True # Assume it is the last page initially
            for a in page.find_all("a"):    # Find the Next page button
                if a.has_attr("class") and len(a["class"]) == 2:
                    if a["class"][0] == "button" and a["class"][1] =="next":

                        # Remove /search... from string and append new search
                        url = str(start_page[:-17]) + a.get('href')
                        # Add next button link to list of index URLS
                        urls.append(str(url))
                        # Request the next page
                        response = requests.get(url)
                        # Create BeautifulSoup object
                        page = bs4(response.content, "lxml")
                        if TESTING == True:
                            last = True
                        else:
                            last = False    # Not the last page

        return urls     # Return list of URLS to parse

    def parse(self, response):
        """ Parses initial URL. Forwards to propertySetup to get/set attributes.
            parse(object -> None)
        """

        soup = bs4(response.body, "lxml")             # Convert to bs4 object
        rows = soup.select("[class~=result-title] ")  # Div with results

        if rows:            # If there are results on the page
            for n in rows:  # For each listing in results
                url = current_url + str(n.get('href'))  # Link to listing
                yield scrapy.Request(url=url, callback=self.propertySetup)
                if TESTING == True:
                    break

    def propertySetup(self, response):
        """ Creates propertyListing class instance from html_response. Then
            creates a dict with property attributes. Adds dict to property_data.

            propertySetup(object) -> Dict
        """

        soup = bs4(response.body, "html.parser")

        l = propertyListing(soup)
        a = l.attributes()

        prop = {
                    "ID"        : l.propertyID(),
                    "URL"       : response.url,
                    "address"   : l.address(),           # Map street address
                    "area"      : str(l.area()[0]),      # I.e New York
                    "sub_area"  : str(l.area()[1]),      # I.e Brooklyn
                    "post_time" : str(l.postTime()),     # Datetime posted
                    "rentpw"    : str(l.rentPw()),
                    "bedrooms"  : str(l.rooms()["beds"]),
                    "bathrooms" : str(l.rooms()["baths"]),
                    "sqft"      : str(l.sqft()),
                    "laundry"   : str(a["laundry"]),     # Laundry facilities
                    "house_type": str(a["house_type"]),
                    "dogs"      : str(a["dogs"]),        # Are dogs allowed
                    "cats"      : str(a["cats"]),
                    "furnished" : str(a["furnished"]),
                    "garage"    : str(a["garage"]),      # Type of garage
                    "smoking"   : str(a["smoking"]),
                    "accessible": str(a["accessible"]),  # Wheelchair accessible
                    "available" : str(a["available"]),   # Date available
                    # "desc"      : str(l.description),  # User created descrip.
                    "images"    : l.productImages(),     # List of image URLs
                    "location"  : {
                        "lat": str(l.location()[0]),
                        "long": str(l.location()[1])
                        }
                }

        # Add property to dictionary of properties
        property_data[str(prop["ID"])] = prop

    def send_email(self, recipient):
        # SEND EMAIL - http://bit.ly/2hlCdMe
        # Create email object
        msg = MIMEMultipart('alternative')
        # Set email attributes
        msg['Subject'] = "Your Scraping Results"
        msg['From']    = "joshua.bitossi@gmail.com"
        msg['To']      = "joshua.bitossi@gmail.com"

        text = "Scraping results are done"
        html = """\
        <html>
          <head></head>
          <body>
            <p>Hi!<br>
               How are you?<br>
               Here is the <a href="http://www.python.org">link</a> you wanted.
            </p>
          </body>
        </html>
        """

        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')

        msg.attach(part1)
        msg.attach(part2)

        # Send email
        s = smtplib.SMTP('localhost')
        s.sendmail(me, you, msg.as_string())
        s.quit()

    def spider_closed(self, spider):
        """ Actions to take when spider has finished. Writes property data to
            text file.

            spider_closed(object) -> None
            """

        print("Scraped " + str(len(property_data)) + " property listings")
        try:
            with open("properties.txt", 'a') as f: # e.g Newyork.txt
                    json.dump(property_data, f)
            f.close()
        except Exception as e:
            print(e)

class propertyListing():
    def __init__(self, soup):
        self.page = soup

    def area(self):
        """ Returns the breadcrumb section which includes area and search category.
            area(obj) -> [str,str,str,str] - > [Area,SubArea,Search,SubSearch]
        """

        area = []

        for li in self.page.find_all("li"):
            try:
                if (li.p.a):
                    area.extend(li.p.a)
            except AttributeError as e:
                break
        return area

    def postTime(self):
        """ Returns the datetime the listing was posted
            postTime(obj) -> datetime
         """

        return self.page.time["datetime"]

    def rentPw(self):
        """ Returns the price of the listing
            rentPw(obj) - > str
        """

        price = ""

        for span in self.page.find_all("span"):
            try:
                if (span["class"][0] == "price"):
                    price = span.string[1::]    # Remove dollar sign
                    break
            except:
                break
        return price

    def rooms(self):
        """ Returns the number of bedrooms and bathrooms of listing.
            rooms(obj) -> dict(beds: str, baths: str)
        """

        rooms = {"beds" : "", "baths" : ""}

        for p in self.page.find_all("p"):
            try:
                if p.has_attr("class") and p["class"][0] == "attrgroup":

                    count = 0
                    for b in p.span:
                        # TODO: figure out more elegant solution involving dict keys

                        if "/" not in b:    # Annoying seperator
                            if count == 0:
                                rooms["beds"] = b.string.replace("BR", "")
                                count = count + 1
                            elif count == 1:
                                rooms["baths"] = b.string.replace("Ba", "")
                                count = count + 1
                            else:
                                rooms["Misc" + str(count)] = b.stringr
                                count = count + 1

                    # There are at least two attrgroup instances. The second refers
                    # to pets and isn't on every property self.page. This function breaks
                    # before getting to any of the others
                    break

            except:     # If cannot find the bed / baths
                rooms["beds"] = "N.A"
                rooms["baths"] = "N.A"

        return(rooms)

    def sqft(self):
        """ Returns the sq footage of the property if available.
            sqft(object) -> int
        """
        # Sqft doens't use any class or id
        sqft = ""
        for span in self.page.find_all("span"):
            if span.b and len(span) == 3:
                span_items = [] # each tag within the span
                for n in span:
                    span_items.extend(span)
                if span_items[1] == "ft":
                    sqft = span_items[0].string

        return sqft

    def propertyID(self):
        """ Obtains the unique ID given to each listing by craigslist.

            propertyID(object) -> string
        """

        for p in self.page.find_all("p"):
            if p.has_attr("class") and p["class"][0] == "postinginfo":
                if p.string:
                    return (p.string[9::])

    def location(self) :
        """ Provides lat and long of the property.

        location(object) -> list[lat,long]
        """

        location = ["N.A","N.A"]

        for div in self.page.find_all("div"):
            if div.has_attr("data-accuracy"):
                location[0] = str(div["data-latitude"])
                location[1] = str(div["data-longitude"])
                break
        return location

    def address(self):
        """ Uses the mapaddress to determine to property's address.

        address(object) -> str
        """

        address = "N.A"

        for div in self.page.find_all("div"):
            if div.has_attr("class") and div["class"][0] == "mapaddress":
                address = div.string
                return address
                break

    def attributes(self):
        """ Attributes about the property that the user can filter by.
            attributes(object) -> dict
        """
        attributes = {
            "house_type"    : "N.A",
            "garage"        : "N.A",
            "laundry"       : "N.A",
            "furnished"     : False,
            "dogs"          : False,
            "cats"          : False,
            "smoking"       : True,
            "accessible"    : False,
            "available"     : "",
            "desc"          : ""
        }

        for p in self.page.find_all("p"):
            try:
                if p.has_attr("class") and p["class"][0] == "attrgroup":
                    for span in p.find_all("span"):
                        if span.string:
                            # House Type
                            if "apartment" in span.string:
                                attributes["house_type"] = "apartment"

                            elif "condo" in span.string:
                                attributes["house_type"] = "condo"

                            elif "cottage/cabin" in span.string:
                                attributes["house_type"] = "cottage/cabin"

                            elif "duplex" in span.string:
                                attributes["house_type"] = "duplex"

                            elif "flat" in span.string:
                                attributes["house_type"] = "flat"

                            elif "house" in span.string:
                                attributes["house_type"] = "house"

                            elif "in-law" in span.string:
                                attributes["house_type"] = "in-law"

                            elif "loft" in span.string:
                                attributes["house_type"] = "loft"

                            elif "townhouse" in span.string:
                                attributes["house_type"] = "townhouse"

                            elif "manufactured" in span.string:
                                attributes["house_type"] = "manufactured"

                            elif "assisted living" in span.string:
                                attributes["house_type"] = "assisted living"

                            elif "land" in span.string:
                                attributes["house_type"] = "land"

                            # Garage
                            if "carport" in span.string:
                                attributes["garage"] = "carport"
                            elif "attached garage" in span.string:
                                attributes["garage"] = "attached garage"
                            elif "detached garage" in span.string:
                                attributes["garage"] = "detached garage"
                            elif "off-street parking" in span.string:
                                attributes["garage"] = "off-street parking"
                            elif "street parking" in span.string:
                                attributes["garage"] = "street parking"
                            elif "valet parking" in span.string:
                                attributes["garage"] = "valet parking"

                            # Laundry
                            if "w/d in unit" in span.string:
                                attributes["laundry"] = "Washer dryer in unit"
                            elif "w/d hookups" in span.string:
                                attributes["laundry"] = "Washer dryer hookups"
                            elif "laundry in bldg" in span.string:
                                attributes["laundry"] = "Laundry in Building"
                            elif "laundry on site" in span.string:
                                attributes["laundry"] = "Laundry on site"
                            elif "no laundry on site" in span.string:
                                attributes["laundry"] = "No laundry on site"

                            # Furnished
                            if "furnished" in span.string:
                                attributes["furnished"] = True
                            # Dogs
                            if "wooof" in span.string:
                                attributes["dogs"] = True
                            # Cats
                            if "purrr" in span.string:
                                attributes["cats"] = True
                            # Smoking
                            if "no smoking" in span.string:
                                attributes["smoking"] = False
                            # Wheelchair Accessible
                            if "wheelchair accessible" in span.string:
                                attributes["wheelchair"] = True

                            # Date available
                            if "available" in span.string:
                                attributes["available"] = span.string[9::]

            except Exception as e:
                print(e)
                return attributes

        return attributes

    def description(self):
        """ Returns the user description of the page.

            description(object) -> string
        """
        for section in self.page.find_all("section"):
            if section.has_attr("id") and section["id"] == "postingbody":
                content = str(section).replace("</section>", "").replace("\n", "").replace("<br/>", "").split('</div>')
                return content[2]

    def productImages(self):
        """ Returns the URLS of the images for the property at start_page URL.

            productImages(string) -> list(string)
        """

        urls = []

        for script in self.page.find_all("script"):
            if script.string and "imgList" in script.string:    # find variable
                try:
                    # Remove HTML script tags and seperate
                    attributes = (script.string[21:-7].split(','))
                    for item in attributes:
                        # Split items into key, value (Use 1 to avoid split at http://)
                        key = item.split(":",1)
                        key[0].replace('"', "") # e.g URL
                        key[1].replace('"', "") # e.g  Http://images.c....

                        if key[0] == '"url"':
                            urls.append(key[1].replace('"', ""))

                    return (urls)

                except Exception as e:
                    print ("Error" + str(e))
