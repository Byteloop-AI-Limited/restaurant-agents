from sfcs_agent.identity import IDENTITY, PRESENTATION


def test_sfcs_identity_is_app_owned():
    assert IDENTITY.rest_ref == "SFCS"
    assert IDENTITY.waba_namespace == "sfcs"
    assert "Southern Fried Chicken" in PRESENTATION.display_name
    assert [option.title for option in PRESENTATION.enquiry_menu.options] == [
        "Share feedback",
        "Subscribe for offers",
    ]
    assert PRESENTATION.enquiry_button_label == "More options"
