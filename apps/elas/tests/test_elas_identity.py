from elas_agent.identity import IDENTITY, PRESENTATION, RESTAURANT_SELECTION


def test_elas_identity_is_app_owned():
    assert IDENTITY.rest_ref == "ELAS"
    assert IDENTITY.waba_namespace == "elas"
    assert PRESENTATION.display_name == "Elai"
    assert PRESENTATION.contact_phone == "01722656888"
    assert [option.title for option in PRESENTATION.enquiry_menu.options] == [
        "Share feedback",
        "Parking availability",
        "Subscribe for offers",
        "Book a table",
    ]
    book_a_table = PRESENTATION.enquiry_menu.options[-1]
    assert book_a_table.human_message == "I want to book a table"
    assert PRESENTATION.enquiry_button_label == "More options"


def test_book_a_table_is_restricted_to_elai():
    """Wings and Things (CHKS) has supports_dine_in=False, so the enquiry
    menu must hide this row for it rather than rely on transfer_to_dinein's
    guard to decline after the tap — see ADR-0024."""
    options = {option.title: option for option in PRESENTATION.enquiry_menu.options}
    assert options["Book a table"].only_for_rest_refs == ("ELAS",)
    for title in ("Share feedback", "Parking availability", "Subscribe for offers"):
        assert options[title].only_for_rest_refs is None
    assert [
        o.title for o in PRESENTATION.enquiry_menu.visible_options_for("CHKS")
    ] == ["Share feedback", "Parking availability", "Subscribe for offers"]
    assert [
        o.title for o in PRESENTATION.enquiry_menu.visible_options_for("ELAS")
    ] == [
        "Share feedback",
        "Parking availability",
        "Subscribe for offers",
        "Book a table",
    ]


def test_elas_configures_restaurant_selection_including_its_own_identity():
    assert PRESENTATION.restaurant_selection is RESTAURANT_SELECTION
    assert [choice.rest_ref for choice in RESTAURANT_SELECTION.choices] == [
        "ELAS",
        "CHKS",
    ]
    # The app's own identity must be one of the configured choices, or
    # create_restaurant_app refuses to start (see app_factory.py).
    assert RESTAURANT_SELECTION.choice_for(IDENTITY.rest_ref) is not None


def test_only_wings_and_things_is_excluded_from_dine_in():
    elai_choice = RESTAURANT_SELECTION.choice_for("ELAS")
    chks_choice = RESTAURANT_SELECTION.choice_for("CHKS")
    assert elai_choice.supports_dine_in is True
    assert chks_choice.supports_dine_in is False


def test_elas_configures_dine_in_reservation_link():
    assert PRESENTATION.reservation_base_url == "https://elai-reservation.byteloop.ai"
