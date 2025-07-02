from collections import defaultdict, namedtuple
from typing import List

from django import template
from django.urls import reverse

from exchange.controllers import is_exchange_acceptable, is_exchange_cancellable
from exchange.models import Exchange
from friprosveta.models import Activity
from timetable.models import WEEKDAYS, WORKHOURS, Allocation

register = template.Library()


def _exchange_sorted_helper(exchange: Exchange):
    day_map = {}
    hour_map = {}
    for i, (d, _) in enumerate(WEEKDAYS):
        day_map[d] = i
    for i, (h, _) in enumerate(WORKHOURS):
        hour_map[h] = i

    result = day_map.get(exchange.allocation_from.day, -1) * 100 + hour_map.get(
        exchange.allocation_from.start, -1
    )
    if exchange.allocation_to:
        result += day_map.get(exchange.allocation_to.day, -1) * 10 + hour_map.get(
            exchange.allocation_to.start, -1
        )
    return result


@register.inclusion_tag("exchange/template_exchange_list.html")
def render_exchanges(
    exchanges,
    show_subject=True,
    third_person=False,
    manager_student=None,
    show_student=True,
    show_finalized=False,
    show_cancelled=False,
    show_cancel_link=True,
):
    """Directive-like helper.

    Args:
        exchanges (List[Exchange]): A list of exchanges.
        show_subject (bool): Whether to show the subject preceding everything else.
        show_student (bool): Whether to show the student's name, if SPECIFIC_STUDENT.
        third_person (bool): Whether to output third person perspective noun forms.
        manager_student (Student): The student that would accept the exchange. If None, no accept links are generated.
        show_finalized (bool): Whether to display finalized exchanges.
        show_cancelled (bool): Whether to display cancelled exchanges.
        show_cancel_link (bool): Whether to display the cancel button, if available.
    """
    filtered_exchanges = exchanges
    if not show_finalized:
        filtered_exchanges = [e for e in filtered_exchanges if not e.is_finalized()]
    if not show_cancelled:
        filtered_exchanges = [e for e in filtered_exchanges if not e.is_cancelled()]

    # sort exchanges
    sorted_exchanges = sorted(filtered_exchanges, key=_exchange_sorted_helper)

    view_models = []
    vm = namedtuple(
        "ExchangeViewModel",
        [
            "type",
            "allocation_from",
            "allocation_to",
            "initiator_student",
            "requested_finalizer_student",
            "date_created",
            "date_finalized",
            "cancelled",
            "subject",
            "has_initiator_student",
            "accept_link",
            "cancel_link",
        ],
    )
    for ex in sorted_exchanges:
        subject = Activity.from_timetable_activity(
            ex.allocation_from.activityRealization.activity
        ).subject
        view_models.append(
            vm(
                subject="{}".format(subject.name),
                type=ex.get_type().name,
                allocation_from="{} at {}".format(
                    ex.allocation_from.day, ex.allocation_from.start
                ),
                allocation_to="{} at {}".format(
                    ex.allocation_to.day, ex.allocation_to.start
                ),
                has_initiator_student=ex.initiator_student is not None,
                initiator_student="{} {}".format(
                    ex.initiator_student.name.title(),
                    ex.initiator_student.surname.title(),
                )
                if ex.initiator_student is not None
                else None,
                requested_finalizer_student="{}".format(
                    str(ex.requested_finalizer_student)
                ),
                date_created="{}".format(str(ex.date_created)),
                date_finalized="{}".format(str(ex.date_finalized)),
                cancelled=bool(ex.date_cancelled),
                accept_link=reverse(
                    "accept_exchange",
                    kwargs={
                        "timetable_slug": ex.allocation_from.timetable.slug,
                        "exchange_id": ex.id,
                    },
                )
                if manager_student and is_exchange_acceptable(ex, manager_student)
                else None,
                cancel_link=reverse(
                    "cancel_exchange",
                    kwargs={
                        "timetable_slug": ex.allocation_from.timetable.slug,
                        "exchange_id": ex.id,
                    },
                )
                if manager_student and is_exchange_cancellable(ex, manager_student)
                else None,
            )
        )

    return {
        "exchanges": view_models,
        "show_subject": show_subject,
        "show_student": show_student,
        "show_cancel_link": show_cancel_link,
        "source_word": "Their" if not third_person else "From",
        "destination_word": "for your" if not third_person else "to",
    }
