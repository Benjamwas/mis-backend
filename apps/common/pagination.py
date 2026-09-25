"""Standard pagination returning the SALA envelope-compatible meta block."""
from collections import OrderedDict

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data):
        next_page = self.get_next_link()
        previous_page = self.get_previous_link()
        return Response(
            OrderedDict(
                [
                    ("data", data),
                    (
                        "meta",
                        OrderedDict(
                            [
                                ("page", self.page.number),
                                ("page_size", self.get_page_size(self.request)),
                                ("total", self.page.paginator.count),
                                ("total_pages", self.page.paginator.num_pages),
                                ("next", next_page),
                                ("previous", previous_page),
                            ]
                        ),
                    ),
                ]
            )
        )