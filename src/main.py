import os
import supervisely as sly
import supervisely.app.development as sly_app_development
from supervisely.app.widgets import Container, Button, Field, Table, Text
from dotenv import load_dotenv

columns = ["Status", "Dataset name", "Video ID", "Video Name", "URL", "Object Name", "Frame Range"]
ok_status = "✅"
error_status = "❌"

check_button = Button("Check")
check_field = Field(
    title="Check the labeling job",
    description="Press the button to check if the labeling job is meeting the requirements",
    content=check_button,
)

error_text = Text(
    "Some objects are not labeled correctly. Please check the results table for more details.",
    status="error",
)
error_text.hide()

results_table = Table(columns=columns, fixed_cols=1)
results_table.hide()

layout = Container(widgets=[check_field, error_text, results_table])
app = sly.Application(layout=layout)

# Enabling advanced debug mode.
if sly.is_development():
    load_dotenv("local.env")
    team_id = sly.env.team_id()
    load_dotenv(os.path.expanduser("~/supervisely.env"))
    # sly_app_development.supervisely_vpn_network(action="up")
    # sly_app_development.create_debug_task(team_id, port="8000")

api = sly.Api.from_env()
project_id = sly.env.project_id()
project_meta = sly.ProjectMeta.from_json(api.project.get_meta(project_id))

results = []


@check_button.click
def check():
    results.clear()
    results_table.hide()
    error_text.hide()

    datasets = api.dataset.get_list(project_id)
    for dataset in datasets:
        video_infos = api.video.get_list(dataset.id)
        video_ids = [video_info.id for video_info in video_infos]
        video_names = [video_info.name for video_info in video_infos]
        anns = download_annotations(dataset.id, video_ids)

        for video_id, video_name, ann in zip(video_ids, video_names, anns):
            check_annotation(dataset, video_id, video_name, ann)

    results_table.read_json({"columns": columns, "data": results})
    results_table.show()

    if any([result[0] == error_status for result in results]):
        error_text.show()


def download_annotations(dataset_id, video_ids):
    anns_json = api.video.annotation.download_bulk(dataset_id, video_ids)
    return [
        sly.VideoAnnotation.from_json(ann_json, project_meta, key_id_map=sly.KeyIdMap())
        for ann_json in anns_json
    ]


def check_annotation(
    dataset: sly.DatasetInfo, video_id: int, video_name: str, ann: sly.VideoAnnotation
):
    for tag in ann.tags:
        status = ok_status if is_in_range(tag, ann) else error_status
        results.append(
            [
                status,
                dataset.name,
                video_id,
                video_name,
                sly.video.get_labeling_tool_link(
                    sly.video.get_labeling_tool_url(
                        dataset.id, video_id, video_frame=tag.frame_range[0]
                    )
                ),
                tag.value,
                tag.frame_range,
            ]
        )


def is_in_range(tag: sly.VideoTag, ann: sly.VideoAnnotation) -> bool:
    range_start, range_end = tag.frame_range
    for figure in ann.figures:
        if figure.video_object.obj_class.name == tag.value:
            if figure.frame_index in range(range_start, range_end + 1):
                return True
    return False
