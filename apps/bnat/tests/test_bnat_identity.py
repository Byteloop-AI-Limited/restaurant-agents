from bnat_agent.identity import IDENTITY, PRESENTATION


def test_bnat_identity_is_app_owned():
    assert IDENTITY.rest_ref == "BNAT"
    assert IDENTITY.waba_namespace == "bnat"
    assert PRESENTATION.display_name == "Burger Nation"
