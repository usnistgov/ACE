import asyncio

from kafka import KafkaProducer
from nats.aio.client import Client as NATS
from nats.aio.errors import ErrConnectionClosed, ErrNoServers, ErrTimeout

from ace import analytic_pb2


class NATSProducer:
    def __init__(self, addr, value_serializer=None, loop=None):
        """Light wrapper on a NATS client used to generate data and push it into a NATS subject."""
        self.nc = NATS()
        self.value_serializer = value_serializer or (lambda value: value.encode())
        self.loop = loop or asyncio.get_event_loop()
        self.loop.run_until_complete(self.connect(addr))

    async def connect(self, addr):
        await self.nc.connect(addr)

    def send(self, subject, msg):
        """ Pushes data into a NATS subject"""
        pub = self.nc.publish(subject, self.value_serializer(msg))
        self.loop.run_until_complete(pub)


class NATSConsumer:
    def __init__(self, addr, value_deserializer=None, loop=None, callback_func=None):
        """
        Light wrapper on a NATS client used to subscribe to a NATS subject and pull
        data from it. Default behavior is to print data to stdout as it is received. 

        A callback function may be specified. As data is pulled from the NATS subject, 
        this function is called with the decoded data as it's argument.

        By default the `.decode()` method is used to decode the data, but a custom value_deserializer
        may be specified. This function will recieve the data (as a byte string) as an argument and 
        return the decoded value.
        """

        self.nc = NATS()
        self.value_deserializer = value_deserializer or (lambda data: data.decode())
        self.loop = loop or asyncio.get_event_loop()
        self.loop.run_until_complete(self.connect(addr))
        self.callback_func = callback_func or (lambda value: print(value))

    async def subscription_handler(self, msg):
        results = {
            "subject": msg.subject,
            "reply": msg.reply,
            "data": self.value_deserializer(msg.data)
        }
        self.callback_func(results)

    async def connect(self, addr):
        await self.nc.connect(addr)

    def subscribe(self, subject):
        self.loop.run_until_complete(self.nc.subscribe(subject, cb=self.subscription_handler))


class KakfaProducer:
    def __init__(self, addr, value_serializer=None, loop=None):
        self.value_serializer = value_serializer or (lambda value: value.encode())
        self.producer = KafkaProducer(bootstrap_servers=addr, value_serializer=self.value_serializer)

    def send(self, topic, value):
        self.producer.send(subject, message)


class ACEProducer:
    """ 
    Adapter used to interchange between NATS and Kafka message queues. Uses either the 
    KafkaProducer or NATSProducer. Both classes have the same signature for the `__init__` 
    method and for the send method allowing for one to code systems using this class regardless
    of whether Kafka or NATS is used as the messaging system.

    The messaging system (Kafka/NATS) can be specified with messenger_type.

    The method used to serialize data can be specified with `value_serializer`
    """

    def __init__(self, addr, value_serializer=None, messenger_type="NATS", loop=None):
        self.messenger_type = messenger_type
        producer_class = MESSENGER.get(messenger_type)
        if not producer_class:
            raise ValueError("Invalid messenger type specified. Got {}. Supported types are {}".format(messenger_type, list(MESSENGER.keys())))
        self.producer = producer_class(addr=addr, value_serializer=value_serializer, loop=loop)

    def send(self, subject, msg):
        """ Push the data in 'msg; into the queue with name `subject` """
        self.producer.send(subject, msg)


MESSENGER = {
    "NATS": NATSProducer,
    "Kafka": KafkaProducer
}


def ace_example_consumer(subject, loop, m_type="NATS"):
    consumer = NATSConsumer(addr="localhost:4222", value_deserializer=lambda value: analytic_pb2.ProcessedFrame().FromString(value), loop=loop)
    consumer.subscribe(subject)


def test():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--subject", default="opencv_object_detector.localhost", help="NATS subject from which to consume")
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    ace_example_consumer(args.subject, loop)
    try:
        loop.run_forever()
    finally:
        loop.close()


if __name__ == "__main__":
    test()
