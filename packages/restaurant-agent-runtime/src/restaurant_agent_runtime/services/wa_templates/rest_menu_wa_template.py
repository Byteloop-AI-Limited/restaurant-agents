"""
WhatsApp restaurant menu carousel template script.
    . Configures PyWa client and fetches WhatsApp template settings for restaurant menus
    . Builds carousel templates and demonstrates sending template-driven promotions
    . Utilizes RestMenuQueryParams for URL query string encoding in template buttons
  Functions/Classes:
    . send_restaurant_menu_carousel
"""

# %%
from typing import Sequence

from pywa.types import (
    Message,
    Template,
    ButtonUrl,
)
from pywa.types.templates import CarouselCard
# from pywa.types.templates import CarouselTemplate
# waba_phone_setting, waba_business_setting

from restaurant_agent_runtime.services.wa_templates.rest_menu_query_params import RestMenuQueryParams


# %% sending carousel
# from pywa.types import HeaderImage, QuickReplyButton, URLButton
from pywa.types.templates import (
    HeaderImage,
    URLButton,
    Carousel,
    BodyText,
    TemplateLanguage,
    TemplateCategory,
    Buttons,
    ParamFormat,
)
# %% Create carousel - Trying to create
# %% Example2 of a single variable

# %% Create carousel - Able to create the Carousel only with one URLButton, 2 resulted in failure; Upload media was not required
carousel_components = [
    card1 := CarouselCard(
        components=[
            hi1 := HeaderImage(
                example="https://placeholder.example.com/menu-images/restaurant-a.jpg"
            ),
            body1 := BodyText(
                text="Browse the menu and place an order with this restaurant.",
            ),
            Buttons(
                buttons=[
                    u1 := URLButton(
                        text="Order Now",
                        url="https://restaurant.ordelo.app/restaurant/{{1}}",
                        example="https://restaurant.ordelo.app/restaurant/restaurant-a",
                    ),
                ]
            ),
        ]
    ),
    card2 := CarouselCard(
        components=[
            hi2 := HeaderImage(
                example="https://placeholder.example.com/menu-images/restaurant-b.jpg"
            ),
            body2 := BodyText(
                text="Browse the menu and place an order with this restaurant.",
            ),
            Buttons(
                buttons=[
                    u2 := URLButton(
                        text="Order Now",
                        url="https://restaurant.ordelo.app/restaurant/{{1}}",
                        example="https://restaurant.ordelo.app/restaurant/restaurant-b",
                    ),
                ]
            ),
        ]
    ),
]

# Wrap the cards with a Carousel component (required)
carousel_menu = Carousel(cards=carousel_components)

# Template-level body text (required for carousel templates)
template_body = BodyText(text="Choose your restaurant")

menu_template = Template(
    name="rest_menu_ui_2",
    language=TemplateLanguage.ENGLISH_US,
    category=TemplateCategory.MARKETING,
    parameter_format=ParamFormat.NAMED,
    components=[template_body, carousel_menu],
)
# %%
# Pass app_id to ensure media examples upload via Upload Resumable API
# runtime.sync_wa_client.create_template(
#     menu_template, app_id=runtime.settings.waba.waa_app_id
# )

# %% Sending the template


def send_restaurant_menu_carousel(
    *,
    recipient: str,
    rest_menu_params: Sequence[RestMenuQueryParams],
    logo_urls: Sequence[str],
    wa_client,
) -> Message:
    """Send the rest_menu_ui_2 template with per-card query parameters."""

    params_list = list(rest_menu_params)
    if len(params_list) != 2:
        raise ValueError(
            "rest_menu_params must contain exactly two RestMenuQueryParams entries."
        )
    logo_list = list(logo_urls)
    if len(logo_list) != 2:
        raise ValueError("logo_urls must contain exactly two entries.")

    first_params, second_params = (
        params_list[0].to_query_params(),
        params_list[1].to_query_params(),
    )

    return wa_client.send_template(
        to=recipient,
        name="rest_menu_ui_2",
        language=TemplateLanguage.ENGLISH_US,
        params=[
            carousel_menu.params(
                cards=[
                    card1.params(
                        index=0,
                        params=[
                            hi1.params(
                                image=logo_list[0]
                            ),
                            u1.params(
                                url_variable=(
                                    f"/{params_list[0].rest_ref.lower()}?{first_params}"
                                ),
                                index=0,
                            ),
                        ],
                    ),
                    card2.params(
                        index=1,
                        params=[
                            hi2.params(
                                image=logo_list[1]
                            ),
                            u2.params(
                                url_variable=(
                                    f"/{params_list[1].rest_ref.lower()}?{second_params}"
                                ),
                                index=0,
                            ),
                        ],
                    ),
                ]
            ),
        ],
    )


# %%


async def send_restaurant_menu_non_carousel(
    *,
    recipient: str,
    rest_menu: RestMenuQueryParams,
    wa_client,
    logo_url: str | None,
    operational_lookups,
):
    """
    Send a non-carousel restaurant menu CTA.

    Uses ORDELO_AGG base URL and current project rest_ref to build the menu link.
    Restaurants without a configured logo receive an equivalent text CTA rather
    than an invalid image send.
    """
    rest_menu_params = (
        rest_menu
        if isinstance(rest_menu, RestMenuQueryParams)
        else RestMenuQueryParams.model_validate(rest_menu)
    )
    rest_ref = rest_menu.rest_ref
    rest_menu_query_params = rest_menu_params.to_query_params()

    restaurant_base_url = operational_lookups.get_app_url("RESTAURANT_MENU")
    restaurant_url = (
        f"{restaurant_base_url}/restaurant/{rest_ref.lower()}?{rest_menu_query_params}"
    )

    if rest_menu_params.order_type == "delivery":
        order_button_title = "Order Delivery"
        caption = "Limited Time Offer - 20% off on all delivery orders"
    else:
        order_button_title = "Order Collection"
        caption = "Get started with your collection order"

    button = ButtonUrl(title=order_button_title, url=restaurant_url)
    if logo_url:
        return await wa_client.send_image(
            to=recipient,
            image=logo_url,
            caption=caption,
            reply_to_message_id=None,
            buttons=button,
        )

    return await wa_client.send_message(
        to=recipient,
        text=caption,
        reply_to_message_id=None,
        buttons=button,
    )
