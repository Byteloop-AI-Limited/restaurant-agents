from bnat_agent.identity import IDENTITY, PRESENTATION


def test_bnat_identity_is_app_owned():
    assert IDENTITY.rest_ref == "BNAT"
    assert IDENTITY.waba_namespace == "bnat"
    assert PRESENTATION.display_name == "Burger Nation Orpington"
    assert PRESENTATION.contact_phone == "01689637476"
    assert PRESENTATION.logo_url is None
    assert [option.title for option in PRESENTATION.enquiry_menu.options] == [
        "Customer complaint",
        "Parking availability",
        "Subscribe for offers",
    ]
