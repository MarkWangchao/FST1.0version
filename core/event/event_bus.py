class EventBus:
    def __init__(self):
        self._subscribers = {}

    def subscribe(self, event_type, subscriber):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(subscriber)

    def unsubscribe(self, event_type, subscriber):
        if event_type in self._subscribers:
            self._subscribers[event_type].remove(subscriber)

    def publish(self, event_type, event):
        if event_type in self._subscribers:
            for subscriber in self._subscribers[event_type]:
                subscriber(event)

class Event:
    def __init__(self, data):
        self.data = data

class EventType:
    EXAMPLE_EVENT = "example_event"