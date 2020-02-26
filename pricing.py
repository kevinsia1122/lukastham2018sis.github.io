import json
import sys
import os 
import random 
import datetime 
import pika 
import uuid 
import csv

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://root@localhost:3306/pricing'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


class Inventory(db.Model):
    __tablename__ = 'inventory'

    itemid = db.Column(db.String(13), primary_key=True)
    itemname = db.Column(db.String(64), nullable=False)
    itemtype = db.Column(db.String(64), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

    def __init__(self, itemid, itemName, itemType, quantity):
        self.itemid = itemid
        self.itemName = itemname
        self.itemType = itemtype
        self.quantity = quantity

    def json(self):
        return {"itemid": self.itemid, "itemname": self.itemname, "itemtype": self.itemtype, "itemquantity": self.quantity}

class Package(db.Model):
    __tablename__ = 'package'

    packageid = db.Column(db.String(13), primary_key=True)
    itemid = db.Column(db.String(13), primary_key=True)
    packagename = db.Column(db.String(13), nullable=False)
    packageprice = db.Column(db.Float(10), nullable=False)
    packagequantity = db.Column(db.Integer, nullable=False)
    no_of_days = db.Column(db.String(13), nullable=False)

    def __init__(self, packagename, packageid, packageprice, packagequantity, itemid, no_of_days):
        self.packagename = packagename
        self.packageid = packageid
        self.packageprice = packageprice
        self.packagequantity = packagequantity
        self.itemid = itemid
        self.no_of_days = no_of_days

    def json(self):
        return {'packagename': self.packagename, 'packageid': self.packageid, 
        'packageprice': self.packageprice, 'itemid': self.itemid, 'no_of_days': self.no_of_days}

@app.route("/package")
def getAllPackage():
    return jsonify({"package": [package.json() for package in Package.query.all()]})

@app.route("/inventory")
def getAllInventory():
    return jsonify({"inventory": [inventory.json() for inventory in Inventory.query.all()]})


def send_price(price):
    """inform Error as needed"""
    # default username / password to the borker are both 'guest'
    hostname = "localhost" # default broker hostname. Web management interface default at http://localhost:15672
    port = 5672 # default messaging port.
    # connect to the broker and set up a communication channel in the connection
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=hostname, port=port))
        # Note: various network firewalls, filters, gateways (e.g., SMU VPN on wifi), may hinder the connections;
        # If "pika.exceptions.AMQPConnectionError" happens, may try again after disconnecting the wifi and/or disabling firewalls
    channel = connection.channel()

    # set up the exchange if the exchange doesn't exist
    exchangename="pricing_topic"
    channel.exchange_declare(exchange=exchangename, exchange_type='topic')

    # prepare the message body content
    message = json.dumps(order, default=str) # convert a JSON object to a string

    # send the message
    # always inform Monitoring for logging no matter if successful or not
    # FIXME: Do you think if this line of code is needed according to the binding key used in Monitoring?
    # channel.basic_publish(exchange=exchangename, routing_key="shipping.info", body=message)
        # By default, the message is "transient" within the broker;
        #  i.e., if the monitoring is offline or the broker cannot match the routing key for the message, the message is lost.
        # If need durability of a message, need to declare the queue in the sender (see sample code below).

    if "status" in order: # if some error happened in order creation
        # inform Error handler
        channel.queue_declare(queue='errorhandler', durable=True) # make sure the queue used by the error handler exist and durable
        channel.queue_bind(exchange=exchangename, queue='errorhandler', routing_key='*.error') # make sure the queue is bound to the exchange
        channel.basic_publish(exchange=exchangename, routing_key="pricing.error", body=message,
            properties=pika.BasicProperties(delivery_mode = 2) # make message persistent within the matching queues until it is received by some receiver (the matching queues have to exist and be durable and bound to the exchange)
        )
        print("Order status ({:d}) sent to error handler.".format(order["status"]))
    else: # inform Shipping and exit
        # prepare the channel and send a message to Shipping
        channel.queue_declare(queue='order', durable=True) # make sure the queue used by Shipping exist and durable
        channel.queue_bind(exchange=exchangename, queue='order', routing_key='*.order') # make sure the queue is bound to the exchange
        channel.basic_publish(exchange=exchangename, routing_key="pricing.order", body=message,
            properties=pika.BasicProperties(delivery_mode = 2, # make message persistent within the matching queues until it is received by some receiver (the matching queues have to exist and be durable and bound to the exchange, which are ensured by the previous two api calls)
            )
        )
        print("Price changes sent to Order.")
    # close the connection to the broker
    connection.close()



if __name__ == '__main__':
    app.run(port=5000, debug=True)

