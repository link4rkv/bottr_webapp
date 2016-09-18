"""
A simple web based real time send/receive text system using
            Tornado + Websocket + Rabbitmq + Mongodb.
"""

from __future__ import print_function
import os

import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.websocket
from tornado.options import options, define

import pika
from pika.adapters.tornado_connection import TornadoConnection

from pymongo import MongoClient

# Define available options
define("port", default=8888, type=int, help="run on the given port")
define("cookie_secret", help="random cookie secret")
define("queue_host", default="127.0.0.1", help="Host for amqp daemon")
define("queue_user", default="guest", help="User for amqp daemon")
define("queue_password", default="guest", help="Password for amqp daemon")

PORT = 8888


class PikaClient(object):

    def __init__(self):

        # Construct a queue name we'll use for this instance only

        #Giving unique queue for each consumer under a channel.
        self.queue_name = "queue-%s" % (id(self),)
        # Default values
        self.connected = False
        self.connecting = False
        self.connection = None
        self.channel = None

        #Webscoket object.
        self.websocket = None

    def connect(self):

        if self.connecting:
                print('PikaClient: Already connecting to RabbitMQ')
                return

        print('PikaClient: Connecting to RabbitMQ on localhost:5672, Object: %s' % (self,))

        self.connecting = True

        credentials = pika.PlainCredentials('guest', 'guest')
        param = pika.ConnectionParameters(host='localhost',
                                          port=5672,
                                          virtual_host="/",
                                          credentials=credentials)
        self.connection = TornadoConnection(param,
                                            on_open_callback=self.on_connected)

        #Currently this will close tornado ioloop.
        #self.connection.add_on_close_callback(self.on_closed)

    def on_connected(self, connection):
        print('PikaClient: Connected to RabbitMQ on localhost:5672')
        self.connected = True
        self.connection = connection
        self.connection.channel(self.on_channel_open)

    def on_channel_open(self, channel):

        print('PikaClient: Channel Open, Declaring Exchange, Channel ID: %s' %
              (channel,))
        self.channel = channel

        self.channel.exchange_declare(exchange='tornado',
                                      type="direct",
                                      auto_delete=True,
                                      durable=False,
                                      callback=self.on_exchange_declared)

    def on_exchange_declared(self, frame):
        print('PikaClient: Exchange Declared, Declaring Queue')
        self.channel.queue_declare(auto_delete=True,
                                   queue=self.queue_name,
                                   durable=False,
                                   exclusive=True,
                                   callback=self.on_queue_declared)

    def on_queue_declared(self, frame):

        print('PikaClient: Queue Declared, Binding Queue')
        self.channel.queue_bind(exchange='tornado',
                                queue=self.queue_name,
                                routing_key='tornado.*',
                                callback=self.on_queue_bound)

    def on_queue_bound(self, frame):
        print('PikaClient: Queue Bound, Issuing Basic Consume')
        self.channel.basic_consume(consumer_callback=self.on_pika_message,
                                   queue=self.queue_name,
                                   no_ack=True)

    def on_pika_message(self, channel, method, header, body):
        print('PikaClient: Message receive, delivery tag #%i' %
              method.delivery_tag)

        #Send the Consumed message via Websocket to browser.
        self.websocket.write_message(body)
        
        #Save the consumed message to mongodb
        self.mongo = Mongodb()
        self.mongo.db = self.mongo.get_db()
        print(self.mongo.get_message(self.mongo.db))
        if self.mongo.get_message(self.mongo.db):
            self.mongo.update_message(self.mongo.db, body)
        else:
            self.mongo.add_message(self.mongo.db, body)

    def on_basic_cancel(self, frame):
        print('PikaClient: Basic Cancel Ok')
        # If we don't have any more consumer processes running close
        self.connection.close()

    def on_closed(self, connection):
        # We've closed our pika connection so stop the demo
        tornado.ioloop.IOLoop.instance().stop()

    def sample_message(self, ws_msg):
        #Publish the message from Websocket to RabbitMQ
        properties = pika.BasicProperties(
            content_type="text/plain", delivery_mode=1)

        self.channel.basic_publish(exchange='tornado',
                                   routing_key='tornado.*',
                                   body=ws_msg,
                                   properties=properties)


class Sample(tornado.web.RequestHandler):

    @tornado.web.asynchronous
    def get(self):
        #get the message from db
        self.mongo = Mongodb()
        self.mongo.db = self.mongo.get_db()
        print(self.mongo.get_message(self.mongo.db))
        if self.mongo.get_message(self.mongo.db):
            message = self.mongo.get_message(self.mongo.db)['message']
        else:
            message = ''

        # Send our main document
        self.render("index.html",
                    connected=self.application.pika.connected, message=message)


class WebSocketServer(tornado.websocket.WebSocketHandler):
    'WebSocket Handler, Which handle new websocket connection.'

    def open(self):
        'Websocket Connection opened.'

        #Initialize new pika client object for this websocket.
        self.pika_client = PikaClient()

        #Assign websocket object to a Pika client object attribute.
        self.pika_client.websocket = self

        ioloop.add_timeout(1000, self.pika_client.connect)

    def on_message(self, msg):
        'A message on the Websocket.'

        #Publish the received message on the RabbitMQ
        self.pika_client.sample_message(msg)

    def on_close(self):
        'Closing the websocket..'
        print("WebSocket Closed")

        #close the RabbiMQ connection...
        self.pika_client.connection.close()


class TornadoWebServer(tornado.web.Application):
    ' Tornado Webserver Application...'
    def __init__(self):

        #Url to its handler mapping.
        handlers = [(r"/ws_channel", WebSocketServer),
                    (r"/sample", Sample)]

        #Other Basic Settings..
        settings = dict(
            cookie_secret=options.cookie_secret,
            login_url="/signin",
            template_path=os.path.join(os.path.dirname(__file__),
                                       "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            xsrf_cookies=True,
            debug=True)

        #Initialize Base class also.
        tornado.web.Application.__init__(self, handlers, **settings)

class Mongodb():
    def __init__(self):
        self.client = MongoClient('localhost:27017') 
    
    def get_db(self):
        db = self.client.bottr
        return db

    def add_message(self, db, msg):
        db.messages.insert({"_id" : 1234, "message" : msg})
    
    def get_message(self, db):
        if db.messages.find():
            return db.messages.find_one({"_id" : 1234})
        else:
            return db.messages.find()

    def update_message(self, db, msg):
        db.messages.update_one({"_id" : 1234}, {"$set" : { "message" : msg } } ) 

if __name__ == '__main__':

    #Tornado Application
    print("Initializing Tornado Webapplications settings...")
    application = TornadoWebServer()

    # Helper class PikaClient makes coding async Pika apps in tornado easy
    pc = PikaClient()
    application.pika = pc  # We want a shortcut for below for easier typing

    # Start the HTTP Server
    print("Starting Tornado HTTPServer on port %i" % PORT)
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(PORT)

    # Get a handle to the instance of IOLoop
    ioloop = tornado.ioloop.IOLoop.instance()

    # Add our Pika connect to the IOLoop since we loop on ioloop.start
    #ioloop.add_timeout(1000, application.pika.connect)

    # Start the IOLoop
    ioloop.start()
