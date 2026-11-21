"""REST endpoints for the CZ studio interface (served at /cz/)."""

from fastapi import Body, Depends, Request

from app.controllers import base
from app.controllers.v1.base import new_router
from app.controllers.v1 import video as video_controller
from app.models.exception import HttpException
from app.services import cz as cz_service
from app.utils import utils

router = new_router(dependencies=[Depends(base.verify_token)])


def _bad_request(request: Request, error: Exception):
    raise HttpException(
        task_id="",
        status_code=400,
        message=f"{base.get_task_id(request)}: {error}",
    )


@router.get("/cz/status", summary="CZ readiness and option lists")
def cz_status():
    return utils.get_response(200, cz_service.status())


@router.post("/cz/settings", summary="Save CZ keys (LLM, Higgsfield)")
def cz_settings(request: Request, body: dict = Body(...)):
    try:
        return utils.get_response(200, cz_service.save_settings(body))
    except ValueError as error:
        _bad_request(request, error)


@router.get("/cz/trends", summary="Trend list for the CZ sidebar")
def cz_trends():
    return utils.get_response(200, cz_service.get_trends())


@router.put("/cz/trends", summary="Replace the trend list")
def cz_save_trends(body: dict = Body(...)):
    items = body.get("items") if isinstance(body.get("items"), list) else []
    return utils.get_response(
        200, cz_service.save_trends(items, str(body.get("updated", "")))
    )


@router.post("/cz/plan", summary="Write script and clip prompts (no video cost)")
def cz_plan(request: Request, body: dict = Body(...)):
    try:
        return utils.get_response(200, cz_service.build_plan(body))
    except ValueError as error:
        _bad_request(request, error)


@router.post("/cz/render", summary="Render a plan into a video with Higgsfield clips")
def cz_render(request: Request, body: dict = Body(...)):
    if body.get("confirm_charge") is not True:
        _bad_request(request, ValueError("confirm_charge must be true"))
    try:
        params = cz_service.build_video_params(body)
    except ValueError as error:
        _bad_request(request, error)
    return video_controller.create_task(request, params, stop_at="video")


@router.get("/cz/projects", summary="Saved CZ projects")
def cz_projects():
    return utils.get_response(200, {"projects": cz_service.list_projects()})


@router.post("/cz/projects", summary="Create or update a CZ project")
def cz_save_project(request: Request, body: dict = Body(...)):
    try:
        return utils.get_response(200, cz_service.save_project(body))
    except ValueError as error:
        _bad_request(request, error)


@router.delete("/cz/projects/{project_id}", summary="Delete a CZ project")
def cz_delete_project(request: Request, project_id: str):
    try:
        cz_service.delete_project(project_id)
    except ValueError as error:
        _bad_request(request, error)
    return utils.get_response(200, {"deleted": project_id})


@router.post("/cz/trends/analyze", summary="Let the text model rank 10 trend formats")
def cz_analyze_trends(request: Request, body: dict = Body(...)):
    try:
        return utils.get_response(
            200,
            cz_service.generate_trends(
                str(body.get("niche", "")).strip(), str(body.get("platform", "")).strip()
            ),
        )
    except ValueError as error:
        _bad_request(request, error)


@router.post("/cz/update", summary="Pull the newest CZ version from GitHub")
def cz_update(request: Request):
    try:
        return utils.get_response(200, cz_service.run_update())
    except (RuntimeError, OSError) as error:
        _bad_request(request, error)


@router.post("/cz/restart", summary="Restart the CZ desktop app")
def cz_restart():
    return utils.get_response(200, {"restarting": cz_service.restart_app()})
