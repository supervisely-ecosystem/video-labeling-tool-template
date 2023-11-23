import os
import supervisely as sly
import supervisely.app.development as sly_app_development
from supervisely.app.widgets import Container, Button, Field
from dotenv import load_dotenv

check_button = Button("Check")
check_field = Field(
    title="Check the labeling job",
    description="Press the button to check if the labeling job is meeting the requirements",
    content=check_button,
)

layout = Container(widgets=[check_field])
app = sly.Application(layout=layout)

# Enabling advanced debug mode.
if sly.is_development():
    load_dotenv("local.env")
    team_id = sly.env.team_id()
    load_dotenv(os.path.expanduser("~/supervisely.env"))
    sly_app_development.supervisely_vpn_network(action="up")
    sly_app_development.create_debug_task(team_id, port="8000")


@check_button.click
def check():
    print("Checking the labeling job...")
