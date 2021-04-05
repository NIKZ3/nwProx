import socket
import _thread
import mysql.connector
import json
import gzip
from http_parser.http import HttpStream

config = dict()
config["packetSize"] = 4096
config["dbPort"] = 8080
config["host"] = "0.0.0.0"
config["user"] = "root"
config["password"] = "nanagawade"
config["database"] = "proxy"
config["auth_plugin"] = 'mysql_native_password'
config["serverPort"] = 8081
config["cacheSize"] = 20


class DLLNode:
    def __init__(self, key, val):
        self.val = []
        self.val.append(val)
        self.key = key
        self.prev = None
        self.next = None

    def appendVal(self, data):
        self.val.append(data)

# LRU cache class


class LRUCache:

    def __init__(self, capacity):
        # capacity:  capacity of cache
        # Intialize all variable
        self.capacity = capacity
        self.map = {}
        self.head = DLLNode(0, 0)
        self.tail = DLLNode(0, 0)
        self.head.next = self.tail
        self.tail.prev = self.head
        self.count = 0

    def deleteNode(self, node):
        node.prev.next = node.next
        node.next.prev = node.prev

    def addToHead(self, node):
        node.next = self.head.next
        node.next.prev = node
        node.prev = self.head
        self.head.next = node

    def get(self, key):
        if key in self.map:
            node = self.map[key]
            result = node.val
            self.deleteNode(node)
            self.addToHead(node)
            print('Got the value : {} for the key: {}'.format(result, key))
            return result
        print('Did not get any value for the key: {}'.format(key))
        return -1

    def set(self, key, value):
        print('going to set the (key, value)')
        if key in self.map:
            node = self.map[key]
            node.val = []
            node.appendVal(value)
            self.deleteNode(node)
            self.addToHead(node)
        else:
            node = DLLNode(key, value)
            self.map[key] = node
            if self.count < self.capacity:
                self.count += 1
                self.addToHead(node)
            else:
                del self.map[self.tail.prev.key]
                self.deleteNode(self.tail.prev)
                self.addToHead(node)

    def appendToNode(self, key, data):
        print("---appending Data----")
        self.map[key].appendVal(data)

    def ifKeyPresent(self, key):
        if key in self.map:
            return True
        return False


class server:

    def __init__(self, port):
        self.port = port
        self.proxySocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.proxySocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.proxySocket.bind(('', self.port))
        self.proxySocket.listen(10)
        self.blackListUrls = dict()
        self.blackListUsers = dict()
        self.cache = dict()
        self.lruCache = LRUCache(config["cacheSize"])
        self.cacheSize = config["cacheSize"]

        self.db = mysql.connector.connect(
            host=config["host"],
            port=config["dbPort"],
            user=config["user"],
            password=config["password"],
            database=config["database"],
            auth_plugin=config["auth_plugin"]
        )

        blackListUrlFile = open('blackListUrlFile.txt', 'r')
        data = blackListUrlFile.readlines()

        blackListUsers = open('blacklistUsers.txt', 'r')
        blackListUsersData = blackListUsers.readlines()

        for d in blackListUsersData:
            self.blackListUsers[d] = 1

        for d in data:
            self.blackListUrls[d] = 1

    def initialiseServer(self):

        while 1:
            clientSocket, clientAddr = self.proxySocket.accept()
            print("Opening new request")
            '''_thread.start_new_thread(
                self.serveRequest, (clientSocket, clientAddr))'''
            self.serveRequest(clientSocket, clientAddr)

    def parseRequest(self, request):
        first_line = request.split('\n')[0]

        # get url

        url = first_line.split(' ')[1]
        http_pos = url.find("://")  # find pos of ://
        if (http_pos == -1):
            temp = url
        else:
            temp = url[(http_pos+3):]  # get the rest of url

        port_pos = temp.find(":")  # find the port pos (if any)
        webserver_pos = temp.find("/")

        if webserver_pos == -1:
            webserver_pos = len(temp)

        webserver = ""
        port = -1

        if (port_pos == -1 or webserver_pos < port_pos):

            # default port
            port = 80
            webserver = temp[:webserver_pos]

        else:  # specific port
            port = int((temp[(port_pos+1):])[:webserver_pos-port_pos-1])
            webserver = temp[:port_pos]

        details = dict()
        details["webserver"] = webserver
        details["completeUrl"] = url
        details["port"] = port

        return details

    def insert_if_modified(self, completeUrl, request):

        #cacheHeader = self.checkCache(completeUrl)
        # if(len(cacheHeader) <= 1):
        #   return request

        if not self.lruCache.ifKeyPresent(completeUrl):
            return request

        responseInitial = self.lruCache.get(completeUrl)
        print("-----initial response---------")
        print(responseInitial[0])
        datePos = responseInitial[0].find(b'Date')
        date = responseInitial[0][datePos:datePos+35]
        cacheHeader = date.decode()
        cacheHeader = cacheHeader[6:35]
        # print("----cacheHeader------")
        # print(cacheHeader)
        lines = request.splitlines()
        while lines[len(lines)-1] == '':
            lines.remove('')

        cacheHeader = "If-Modified-Since: " + cacheHeader
        lines.append(cacheHeader)

        request = "\r\n".join(lines) + "\r\n\r\n"
        print("-------conditional get ------")
        print(request)
        return request

    # get modified time of the request
    def getMtime(self):
        print("OK")
    '''endpoint to serve requests'''

    def serveRequest(self, clientSocket, clientAddr):
        '''Creating connection to the client'''
        flag = 0

        # userDataStore can be used to udata data in database
        userDataStore = dict()
        print(clientAddr)
        userDataStore["userIP"] = clientAddr[0]
        while 1:

            # Checking if user is blackListed
            if clientAddr[0] in self.blackListUsers:
                print("----User is blocked will be reported-----")
                userDataStore["blackListUserAccess"] = 1
                userDataStore["blackListUserIP"] = clientAddr[0]
                self.addToDatabase(userDataStore)
                break

            print("----------Waiting for Request-------")
            try:
                clientSocket.settimeout(5)
                request = clientSocket.recv(config["packetSize"])
            except socket.timeout as err:
                print(err)
                print("------Persistent Connection Disconnected-----")
                break

            request = request.decode()
            if(len(request) == 0):
                break
            httpRefererField = "Referer"
            updateToDatabase = not (httpRefererField in request)

            request = request.replace("Proxy-Connection:", "Connection:")
            details = self.parseRequest(request)

            # inserting if modified header if data is in cache
            request = self.insert_if_modified(details["completeUrl"], request)

            if details["webserver"] in self.blackListUrls:
                userDataStore["blackListUrlAccess"] = 1
                userDataStore["blackListUrl"] = details["webserver"]
                print("----IP not allowed you will be reported----")
                self.addToDatabase(userDataStore)
                break

            userDataStore["Url"] = details["webserver"]
            print(details["completeUrl"])
            '''Creating connection to the webServer'''
            if flag == 0:
                webServer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                webServer.settimeout(10)
                try:
                    webServer.connect(
                        (details["webserver"],   details["port"]))
                    flag = 1

                except:
                    print("-----Server Connection Failed------")
                    break

            try:
                webServer.sendall(request.encode())
            except:
                print("----Webserver request sending failed")
                break

            try:
                print("--------waiting for Response----")
                data = webServer.recv(config["packetSize"])

                #! TODO:-insert lat_mtime in if cases
                #!        Add to database appropriately
                modifiedCheck = b'304 Not Modified'
                if data.find(modifiedCheck) >= 0:
                    print("----cache success----")
                    # print(data)
                    print("-----sending cached data----")
                    #cacheData = self.getCacheData(details["completeUrl"])
                    cacheData = self.lruCache.get(details["completeUrl"])
                    for cacheD in cacheData:
                        clientSocket.send(cacheD)

                else:
                    if len(data) > 0:
                        self.lruCache.set(details["completeUrl"], data)
                    while len(data):
                        #self.addResponseToCache(details["completeUrl"], data)
                        clientSocket.send(data)
                        data = webServer.recv(config["packetSize"])
                        if len(data) > 0:
                            self.lruCache.appendToNode(
                                details["completeUrl"], data)

                    '''if updateToDatabase == True:
                        self.addToDatabase(userDataStore)'''

                if updateToDatabase == True:
                    self.addToDatabase(userDataStore)
            except:
                print("Error in receiving data or sending data")
                break

        try:
            clientSocket.close()
            webServer.close()
        except:
            print(
                "Connection to webServer was not opened or there was an error while closing the connection")
        # reply_end = "\r\n\r\n"
        # clientSocket.send(reply_end.encode())

    '''Add data to database'''

    def addToDatabase(self, userDataStore):
        print("-----Adding data to database------")

        dbCursor = self.db.cursor()

        if "blackListUrlAccess" in userDataStore:

            query = "INSERT into blackListWebsiteVisits (userIP,url) values(%s,%s)"
            values = (userDataStore["userIP"], userDataStore["blackListUrl"])
            print("------Inserted Data into blackListWebsiteVisits------")
            dbCursor.execute(query, values)
            self.db.commit()
            print(dbCursor.rowcount, "record inserted.")

        elif "blackListUserAccess" in userDataStore:
            query = "INSERT into blackListUserVisits (userIP) values(%s)"
            values = (userDataStore["blackListUserIP"],)
            print("------Inserted Data into blackListUserAccess------")
            dbCursor.execute(query, values)
            self.db.commit()
            print(dbCursor.rowcount, "record inserted.")

        else:
            query = "INSERT into siteVisits (userIP,url) values(%s,%s)"
            values = (userDataStore["userIP"], userDataStore["Url"])
            print("------Inserted Data into siteVisits------")
            print(values)
            print(self.db)
            dbCursor.execute(query, values)
            self.db.commit()
            print(dbCursor.rowcount, "record inserted.")


s = server(config["serverPort"])
s.initialiseServer()
