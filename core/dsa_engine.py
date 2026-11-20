"""Pure Python data structures used by the Django services."""
from collections import deque
from dataclasses import dataclass
from datetime import timedelta


@dataclass
class Node:
    topic: object
    previous: 'Node | None' = None
    next: 'Node | None' = None


class DoublyLinkedList:
    def __init__(self, topics):
        self.head = self.tail = None
        self.nodes = {}
        for topic in topics:
            node = Node(topic, previous=self.tail)
            if self.tail:
                self.tail.next = node
            else:
                self.head = node
            self.tail = node
            self.nodes[topic.pk] = node

    def postpone(self, topic_id):
        """Shift the selected topic and every subsequent unfinished topic."""
        node = self.nodes[topic_id]
        while node:
            if node.topic.status != 'Completed':
                node.topic.date += timedelta(days=1)
                yield node.topic
            node = node.next


class MaxHeap:
    def __init__(self, entries):
        self.items = list(entries)
        for index in reversed(range(len(self.items) // 2)):
            self._sink(index)

    def _sink(self, index):
        while 2 * index + 1 < len(self.items):
            child = 2 * index + 1
            if child + 1 < len(self.items) and self.items[child + 1] > self.items[child]:
                child += 1
            if self.items[index] >= self.items[child]:
                break
            self.items[index], self.items[child] = self.items[child], self.items[index]
            index = child

    def pop(self):
        highest = self.items[0]
        last = self.items.pop()
        if self.items:
            self.items[0] = last
            self._sink(0)
        return highest


class FeeMap:
    def __init__(self, fees):
        self._by_student = {fee.student_id: fee for fee in fees}

    def lookup(self, student_id):
        return self._by_student.get(student_id)


class IssueQueue:
    def __init__(self, ordered_issues):
        self._queue = deque(ordered_issues)

    def next(self):
        return self._queue.popleft() if self._queue else None

    def __iter__(self):
        return iter(self._queue)
