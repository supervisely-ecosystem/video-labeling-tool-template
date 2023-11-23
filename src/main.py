import os
import supervisely as sly
import supervisely.app.development as sly_app_development
from supervisely.app.widgets import Container, Button, Field, Table
from dotenv import load_dotenv

columns = ["Status", "Video ID", "Video Name", "URL", "Object Name", "Frame Range"]

check_button = Button("Check")
check_field = Field(
    title="Check the labeling job",
    description="Press the button to check if the labeling job is meeting the requirements",
    content=check_button,
)

results_table = Table(columns=columns, fixed_cols=2)
results_table.hide()

layout = Container(widgets=[check_field, results_table])
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
dataset_id = sly.env.dataset_id()
project_meta = sly.ProjectMeta.from_json(api.project.get_meta(project_id))

results = []


@check_button.click
def check():
    results.clear()
    results_table.hide()

    (
        video_ids,
        video_names,
        anns,
    ) = download_annotations(dataset_id)
    for video_id, video_name, ann in zip(video_ids, video_names, anns):
        check_annotation(video_id, video_name, ann)

    update_table()


def update_table():
    results_table.read_json({"columns": columns, "data": results})
    results_table.show()


def download_annotations(dataset_id):
    video_infos = api.video.get_list(dataset_id)
    video_ids = [video_info.id for video_info in video_infos]
    video_names = [video_info.name for video_info in video_infos]
    anns_json = api.video.annotation.download_bulk(dataset_id, video_ids)
    anns = [
        sly.VideoAnnotation.from_json(ann_json, project_meta, key_id_map=sly.KeyIdMap())
        for ann_json in anns_json
    ]
    return video_ids, video_names, anns


def check_annotation(video_id: int, video_name: str, ann: sly.VideoAnnotation):
    for tag in ann.tags:
        status = "✅" if is_in_range(tag, ann) else "❌"
        results.append(
            [
                status,
                video_id,
                video_name,
                sly.video.get_labeling_tool_link(
                    sly.video.get_labeling_tool_url(
                        dataset_id, video_id, video_frame=tag.frame_range[0]
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
