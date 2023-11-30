import os
import supervisely as sly
from typing import List
import supervisely.app.development as sly_app_development
from supervisely.app.widgets import Container, Button, Field, Table, Text, Checkbox
from dotenv import load_dotenv

# Preparing a list of columns for the results table.
columns = ["Status", "Dataset name", "Video ID", "Video Name", "URL", "Object Name", "Frame Range"]

# Preparing the status icons, you can change them and use your own.
ok_status = "✅"
error_status = "❌"

# This is the main button that starts the check.
check_button = Button("Check")
check_field = Field(
    title="Check the labeling job",
    description="Press the button to check if the labeling job is meeting the requirements",
    content=check_button,
)

# Widget for displaying a result of the check.
check_text = Text()
check_text.hide()

# This checkbox allows you to choose which results to show in the table.
# By default, only incorrect results are shown, but you can also show all results.
show_all_checkbox = Checkbox("Show all results")
show_all_field = Field(
    title="Which results to show",
    description="If checked, will be shown both correct and incorrect results, otherwise only incorrect",
    content=show_all_checkbox,
)

# This is the table where the results will be displayed.
results_table = Table(columns=columns, fixed_cols=1, sort_direction="desc")
results_table.hide()

# Preparing the layout of the application and creating the application itself.
layout = Container(widgets=[check_field, show_all_field, check_text, results_table])
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
project_id = None

# We will store the project meta in a dictionary so that we do not have to download it every time.
project_metas = {}

# We will store the results in a list of lists, where each list is a row in the table.
table_rows = []


@app.event(sly.Event.ManualSelected.VideoChanged)
def video_changed(event_api: sly.Api, event: sly.Event.ManualSelected.VideoChanged):
    global api, project_id
    # Saving the current API object and current project ID to the global variables.
    api = event_api
    project_id = event.project_id

    # Using a simple caching mechanism to avoid downloading the project meta every time.
    if event.project_id not in project_metas:
        project_meta = sly.ProjectMeta.from_json(api.project.get_meta(event.project_id))
        project_metas[event.project_id] = project_meta

    # TODO: Lock buttons only on startup
    event_api.img_ann_tool.disable_job_buttons(event.session_id)


@check_button.click
def check():
    # If the button is pressed, we clear the table and hide it,
    # because we will fill the table with new results.
    # We also hide the error message from the previous check
    # and will show it again if there are incorrect results.
    table_rows.clear()
    results_table.hide()
    check_text.hide()

    # Retrieving the list of datasets in the project.
    datasets = api.dataset.get_list(project_id)

    # Iterating over all datasets in the project.
    for dataset in datasets:
        # Retrieving list of VideoInfo objects for the current dataset.
        video_infos = api.video.get_list(dataset.id)

        # Preparing a list of video IDs and video names for the current dataset.
        video_ids = [video_info.id for video_info in video_infos]
        video_names = [video_info.name for video_info in video_infos]

        # Downloading annotations for the current dataset.
        anns = download_annotations(dataset.id, video_ids)

        # Iterating over all videos in the current dataset
        # and checking the annotations for each video.
        for video_id, video_name, ann in zip(video_ids, video_names, anns):
            check_annotation(dataset, video_id, video_name, ann)

    # Filling the table with the results and showing it.
    results_table.read_json({"columns": columns, "data": table_rows})
    results_table.show()

    # Checking if there are incorrect results.
    if any([result[0] == error_status for result in table_rows]):
        # If there are incorrect results, we show the error message
        # and block the job buttons.
        # TODO: Block buttons
        check_text.text = "The labeling job is not meeting the requirements, please check the table"
        check_text.status = "error"
    else:
        # If there are no incorrect results, we show the success message
        # and unlock the job buttons.
        # TODO: Unlock buttons
        check_text.text = "The labeling job is meeting the requirements"
        check_text.status = "success"

    # Showing the check result.
    check_text.show()


def download_annotations(dataset_id: int, video_ids: List[int]) -> List[sly.VideoAnnotation]:
    """Download annotations for the current dataset and return a list of VideoAnnotation objects.

    :param dataset_id: dataset ID
    :type dataset_id: int
    :param video_ids: list of video IDs
    :type video_ids: List[int]
    :return: list of VideoAnnotation objects
    :rtype: List[sly.VideoAnnotation]
    """
    # Downloading annotations for the current dataset in JSON format.
    anns_json = api.video.annotation.download_bulk(dataset_id, video_ids)

    # Retrieving the cached project meta for the current project.
    project_meta = project_metas[project_id]

    # Returning a list of VideoAnnotation objects.
    return [
        sly.VideoAnnotation.from_json(ann_json, project_meta, key_id_map=sly.KeyIdMap())
        for ann_json in anns_json
    ]


def check_annotation(
    dataset: sly.DatasetInfo, video_id: int, video_name: str, ann: sly.VideoAnnotation
) -> None:
    """Checks the annotation for the current video and adds the result to the global
    list of table rows.

    :param dataset: dataset object
    :type dataset: sly.DatasetInfo
    :param video_id: video ID
    :type video_id: int
    :param video_name: video name
    :type video_name: str
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
            dataset.name,
            video_id,
            video_name,
            sly.video.get_labeling_tool_url(
                dataset.id, video_id, frame=tag.frame_range[0], link=True
            ),
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
