import socket
import _thread


class server:

    def __init__(self, port):
        self.port = port
        self.proxySocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.proxySocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.proxySocket.bind(('', self.port))
        self.proxySocket.listen(10)

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
        details["port"] = port

        return details

    def serveRequest(self, clientSocket, clientAddr):
        flag = 0
        while 1:
            print("----------Waiting for Request----")
            try:
                clientSocket.settimeout(5)
                request = clientSocket.recv(4096)
            except socket.timeout as err:
                print(err)
                print("Persistent Connection Disconnected")
                break

            request = request.decode()
            if(len(request) == 0):
                break
            # print(request)

            x = "Referer"
            print("-----Modified Request--------")
            request = request.replace("Proxy-Connection:", "Connection:")
            print(request)
            details = self.parseRequest(request)
            if flag == 0:
                webServer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                webServer.connect((details["webserver"],   details["port"]))
                flag = 1
            webServer.sendall(request.encode())

            print("--------waiting for Response----")
            data = webServer.recv(4096)
            # print(data)
            while len(data):
                # receive data from web server
                clientSocket.send(data)  # send to browser/client
                data = webServer.recv(4096)

        clientSocket.close()
        webServer.close()
        #reply_end = "\r\n\r\n"
        # clientSocket.send(reply_end.encode())


s = server(8080)
s.initialiseServer()
