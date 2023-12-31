import os
from dotenv import load_dotenv
import supervisely as sly
import supervisely.app.development as sly_app_development
from supervisely.app.widgets import (
    Container,
    Button,
    Field,
    Table,
    Text,
    Checkbox,
)


# Preparing a list of columns for the results table.
columns = [
    "Status",
    "Go to Frame",
    "Object Class",
    "Frame Range",
]

# Preparing the status icons, you can change them and use your own.
ok_status = "✅"
error_status = "❌"

# This is the main button that starts the validation.
validate_button = Button("Validate")
validate_field = Field(
    title="Validate current video",
    description="Press the button to check if the video was annotated correctly",
    content=validate_button,
)

# Widget for displaying a result of the validation.
validate_text = Text()
validate_text.hide()

# This checkbox allows you to choose which results to show in the table.
# By default, only incorrect results are shown, but you can also show all results.
show_all_checkbox = Checkbox("Show all results")
show_all_field = Field(
    title="Which results to show",
    description="If checked, will be shown both correct and incorrect results",
    content=show_all_checkbox,
)

# This is the table where the results will be displayed.
results_table = Table(columns=columns, fixed_cols=1, sort_direction="desc")
results_table.hide()

# Preparing the layout of the application and creating the application itself.
layout = Container(
    widgets=[
        validate_field,
        show_all_field,
        validate_text,
        results_table,
    ]
)
app = sly.Application(layout=layout)

# Enabling advanced debug mode.
if sly.is_development():
    load_dotenv("local.env")
    team_id = sly.env.team_id()
    load_dotenv(os.path.expanduser("~/supervisely.env"))
    sly_app_development.supervisely_vpn_network(action="up")
    sly_app_development.create_debug_task(team_id, port="8000")

# Initializing global variables.
api = None
session_id = None
dataset_id = None
video_id = None

# We will store the project meta in a dictionary so that we do not have to download it every time.
project_metas = {}

# We will store the results in a list of lists, where each list is a row in the table.
table_rows = []


# Subscribing to the event of changing the selected video in the Video Labeling Tool.
# to get the current API object and current project ID.
@app.event(sly.Event.ManualSelected.VideoChanged)
def video_changed(event_api: sly.Api, event: sly.Event.ManualSelected.VideoChanged):
    sly.logger.info("Current video was changed")
    global api, session_id, dataset_id, video_id, project_id
    # Saving the event parameters to global variables.
    api = event_api
    session_id = event.session_id
    dataset_id = event.dataset_id
    video_id = event.video_id
    project_id = event.project_id

    # Using a simple caching mechanism to avoid downloading the project meta every time.
    if event.project_id not in project_metas:
        project_meta = sly.ProjectMeta.from_json(api.project.get_meta(event.project_id))
        project_metas[event.project_id] = project_meta

    api.vid_ann_tool.disable_job_controls(session_id)


@validate_button.click
def validate_video():
    # If the button is pressed, we clear the table and hide it,
    # because we will fill the table with new results.
    # We also hide the error message from the previous validation
    # and will show it again if there are incorrect results.
    table_rows.clear()
    results_table.hide()
    validate_text.hide()

    # Retrieving project meta from the cache.
    project_meta = project_metas[project_id]

    # Downloading the annotation in JSON format and converting it to VideoAnnotation object.
    ann_json = api.video.annotation.download(video_id)
    ann = sly.VideoAnnotation.from_json(ann_json, project_meta, key_id_map=sly.KeyIdMap())

    # Validating the annotation for the current video.
    validate_annotation(dataset_id, video_id, ann)

    # Filling the table with the results and showing it.
    if len(table_rows) > 0:
        results_table.read_json({"columns": columns, "data": table_rows})
        results_table.show()

    # Checking if there are incorrect results.
    if any([result[0] == error_status for result in table_rows]):
        # If there are incorrect results, we show the error message
        # and block the job buttons.
        api.vid_ann_tool.disable_job_controls(session_id)
        validate_text.text = "The video was not annotated correctly"
        validate_text.status = "error"
    else:
        # If there are no incorrect results, we show the success message
        # and unlock the job buttons.
        api.vid_ann_tool.enable_job_controls(session_id)
        validate_text.text = "The video is annotated correctly"
        validate_text.status = "success"

    # Showing the validation result.
    validate_text.show()


@results_table.click
def handle_table_button(datapoint: sly.app.widgets.Table.ClickedDataPoint) -> None:
    """Handles clicks on the buttons in the table.
    Changes the current frame in the Labeling Tool to the start frame.

    :param datapoint: ClickedDataPoint object
    :type datapoint: sly.app.widgets.Table.ClickedDataPoint
    """
    if datapoint.button_name != "Open":
        return

    # Getting the frame range from the table row.
    start, end = datapoint.row["Frame Range"]

    # Changing the current frame in the Labeling Tool.
    api.vid_ann_tool.set_video(session_id, video_id, start)


def validate_annotation(dataset_id: int, video_id: int, ann: sly.VideoAnnotation) -> None:
    """Validates the annotation for the current video and adds the result to the global
    list of table rows.

    :param dataset: ID of the dataset where the video is located
    :type dataset: int
    :param video_id: video ID
    :type video_id: int
    :param ann: VideoAnnotation object
    :type ann: sly.VideoAnnotation
    """

    # Iterating over all tags in the current annotation.
    for tag in ann.tags:
        # Checking if there's an object with the same ObjClass name
        # as value of the current tag in the tag's frame range.
        status = ok_status if is_in_range(tag, ann) else error_status

        # Preparing an entry for the results table.
        result = [
            status,
            sly.app.widgets.Table.create_button("Open"),
            tag.value,
            tag.frame_range,
        ]

        # If we're showing all results than we'll add ok results too,
        # otherwise we'll add only incorrect results.
        if show_all_checkbox.is_checked() or status == error_status:
            table_rows.append(result)


def is_in_range(tag: sly.VideoTag, ann: sly.VideoAnnotation) -> bool:
    """Checks if there's an object with the same ObjClass name
    as value of the current tag in the tag's frame range.

    :param tag: VideoTag object
    :type tag: sly.VideoTag
    :param ann: VideoAnnotation object
    :type ann: sly.VideoAnnotation
    :return: True if there's an object with the same ObjClass name
             as value of the current tag in the tag's frame range, False otherwise
    :rtype: bool
    """
    # Retrieving the frame range for the current tag.
    range_start, range_end = tag.frame_range
    for figure in ann.figures:
        if figure.video_object.obj_class.name == tag.value:
            if figure.frame_index in range(range_start, range_end + 1):
                return True
    return False
