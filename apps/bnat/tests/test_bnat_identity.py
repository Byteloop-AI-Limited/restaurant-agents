from bnat_agent.identity import IDENTITY, PRESENTATION


def test_bnat_identity_is_app_owned():
    assert IDENTITY.rest_ref == "BNAT"
    assert IDENTITY.waba_namespace == "bnat"
    assert PRESENTATION.display_name == "Burger Nation Orpington"
    assert PRESENTATION.contact_phone == "01689637476"
    assert (
        PRESENTATION.logo_url
        == "https://ordelo-restaurants.s3.eu-west-2.amazonaws.com/"
        "bnat/bnat_restaurant_menu_url.png"
    )
    assert [option.title for option in PRESENTATION.enquiry_menu.options] == [
        "Share feedback",
        "Parking availability",
        "Subscribe for offers",
    ]
    assert PRESENTATION.delivery_button_label == "Delivery (10%)"
    assert PRESENTATION.takeaway_button_label == "Collection"
    assert PRESENTATION.enquiry_button_label == "More Options"
    assert PRESENTATION.delivery_promo_caption == (
        "Limited-time offer: 10% off delivery orders, or 15% with a valid "
        "coupon code."
    )
    assert PRESENTATION.takeaway_promo_caption == (
        "Limited-time offer: 5% off collection orders over £25."
    )
