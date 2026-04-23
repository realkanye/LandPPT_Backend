"""
LandPPT Pure API Mode - No Authentication, No Web Interface
FastAPI-based REST API for PPT generation functionality
"""

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
import uvicorn
import asyncio
import logging
import os
import sys
from typing import List, Optional, Dict, Any
import uuid

from .api.models import (
    PPTGenerationRequest, PPTOutline, PPTProject,
    TodoBoard, ProjectListResponse, FileUploadResponse,
    FileOutlineGenerationRequest, TemplateSelectionRequest,
    TemplateSelectionResponse, PPTScenario
)
from .services.service_instances import get_ppt_service_for_user
from .services.file_processor import FileProcessor
from .core.config import ai_config, app_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Disable SQLAlchemy verbose logging
logging.getLogger('sqlalchemy').setLevel(logging.WARNING)

# Create FastAPI app
app = FastAPI(
    title="LandPPT API",
    description="AI-powered PPT Generation REST API - Pure API Mode",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Add CORS middleware - allow all origins for API mode
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service instances - use anonymous user for API-only mode
ANONYMOUS_USER_ID = app_config.anonymous_user_id
ppt_service = get_ppt_service_for_user(ANONYMOUS_USER_ID)
file_processor = FileProcessor()


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info("=" * 60)
    logger.info("LandPPT API Server Starting...")
    logger.info(f"Mode: {'API-ONLY (No Auth)' if app_config.disable_auth else 'Standard'}")
    logger.info(f"AI Provider: {ai_config.default_ai_provider}")
    logger.info(f"Anonymous User ID: {ANONYMOUS_USER_ID}")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("LandPPT API Server shutting down...")


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "LandPPT API",
        "version": "1.0.0",
        "api_mode": "pure_api_no_auth",
        "ai_provider": ai_config.default_ai_provider,
        "available_providers": ai_config.get_available_providers()
    }


# ============================================================================
# Scenarios & Templates
# ============================================================================

@app.get("/scenarios", response_model=List[PPTScenario], tags=["Templates"])
async def get_scenarios():
    """Get available PPT scenarios"""
    return [
        PPTScenario(
            id="general",
            name="通用",
            description="适用于各种通用场景的PPT模板，提供专业的商务风格",
            icon="📋",
            template_config={"style": "professional", "color_scheme": "blue", "font_family": "Arial, sans-serif"}
        ),
        PPTScenario(
            id="tourism",
            name="旅游观光",
            description="旅游线路策划、景点介绍、行程规划等旅游相关内容",
            icon="🌍",
            template_config={"style": "vibrant", "color_scheme": "green", "font_family": "Georgia, serif"}
        ),
        PPTScenario(
            id="education",
            name="儿童科普",
            description="教育培训、科普知识、儿童友好的设计风格",
            icon="🎓",
            template_config={"style": "playful", "color_scheme": "rainbow", "font_family": "Comic Sans MS, cursive"}
        ),
        PPTScenario(
            id="analysis",
            name="深入分析",
            description="数据分析、研究报告、学术论文等专业分析内容",
            icon="📊",
            template_config={"style": "analytical", "color_scheme": "dark", "font_family": "Helvetica, sans-serif"}
        ),
        PPTScenario(
            id="history",
            name="历史文化",
            description="历史事件、文化传承、人文艺术等主题",
            icon="🏛️",
            template_config={"style": "classical", "color_scheme": "brown", "font_family": "Times New Roman, serif"}
        ),
        PPTScenario(
            id="technology",
            name="科技技术",
            description="技术介绍、产品发布、创新展示等科技内容",
            icon="💻",
            template_config={"style": "modern", "color_scheme": "purple", "font_family": "Roboto, sans-serif"}
        ),
        PPTScenario(
            id="business",
            name="方案汇报",
            description="商业计划、项目汇报、企业展示等商务场景",
            icon="💼",
            template_config={"style": "corporate", "color_scheme": "navy", "font_family": "Arial, sans-serif"}
        )
    ]


# ============================================================================
# Outline Generation
# ============================================================================

@app.post("/outline/generate", response_model=Dict[str, Any], tags=["Outline"])
async def generate_outline(request: PPTGenerationRequest):
    """Generate PPT outline only"""
    try:
        request.user_id = ANONYMOUS_USER_ID
        outline = await ppt_service.generate_outline(request)
        return {
            "success": True,
            "outline": outline,
            "message": "Outline generated successfully"
        }
    except Exception as e:
        logger.error(f"Error generating outline: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# File Upload & Processing
# ============================================================================

@app.post("/upload", response_model=FileUploadResponse, tags=["Files"])
async def upload_file(file: UploadFile = File(...)):
    """Upload document for PPT generation"""
    try:
        allowed_types = [".docx", ".pdf", ".txt", ".md"]
        file_extension = "." + file.filename.split(".")[-1].lower()

        if file_extension not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type. Allowed types: {', '.join(allowed_types)}"
            )

        content = await file.read()

        processed_content = await ppt_service.process_uploaded_file(
            filename=file.filename,
            content=content,
            file_type=file_extension
        )

        return FileUploadResponse(
            filename=file.filename,
            size=len(content),
            type=file_extension,
            processed_content=processed_content,
            message="File uploaded and processed successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/files/generate-outline", tags=["Files"])
async def generate_outline_from_file(request: FileOutlineGenerationRequest):
    """Generate PPT outline directly from uploaded file content"""
    try:
        result = await ppt_service.generate_outline_from_file_content(request)
        return {
            "success": True,
            "data": result,
            "message": "Outline generated from file successfully"
        }
    except Exception as e:
        logger.error(f"Error generating outline from file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Project Management
# ============================================================================

@app.post("/projects", response_model=PPTProject, tags=["Projects"])
async def create_project(request: PPTGenerationRequest):
    """Create a new PPT project with full workflow"""
    try:
        request.user_id = ANONYMOUS_USER_ID
        project = await ppt_service.create_project_with_workflow(request)
        return project
    except Exception as e:
        logger.error(f"Error creating project: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/projects", response_model=ProjectListResponse, tags=["Projects"])
async def list_projects(
    page: int = 1,
    page_size: int = 10,
    status: Optional[str] = None
):
    """List all projects with pagination"""
    try:
        return await ppt_service.project_manager.list_projects(
            page=page,
            page_size=page_size,
            status=status,
            user_id=ANONYMOUS_USER_ID
        )
    except Exception as e:
        logger.error(f"Error listing projects: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/projects/{project_id}", response_model=PPTProject, tags=["Projects"])
async def get_project(project_id: str):
    """Get project details"""
    try:
        project = await ppt_service.project_manager.get_project(
            project_id,
            user_id=ANONYMOUS_USER_ID
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/projects/{project_id}/todo", response_model=TodoBoard, tags=["Projects"])
async def get_project_todo_board(project_id: str):
    """Get project workflow todo board"""
    try:
        project = await ppt_service.project_manager.get_project(
            project_id,
            user_id=ANONYMOUS_USER_ID
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project.todo_board
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting todo board: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/projects/{project_id}/stages/{stage_id}", tags=["Projects"])
async def update_project_stage(
    project_id: str,
    stage_id: str,
    status: str = "completed",
    result: Optional[Dict[str, Any]] = None
):
    """Update project stage status"""
    try:
        success = await ppt_service.project_manager.update_stage(
            project_id=project_id,
            stage_id=stage_id,
            status=status,
            result=result,
            user_id=ANONYMOUS_USER_ID
        )
        return {
            "success": success,
            "message": "Stage updated successfully" if success else "Stage update failed"
        }
    except Exception as e:
        logger.error(f"Error updating stage: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{project_id}/continue-from-stage", tags=["Projects"])
async def continue_project_from_stage(
    project_id: str,
    stage_index: int = 0
):
    """Resume project workflow from specified stage"""
    try:
        result = await ppt_service.continue_from_stage(
            project_id=project_id,
            stage_index=stage_index,
            user_id=ANONYMOUS_USER_ID
        )
        return {
            "success": True,
            "data": result,
            "message": "Workflow continued successfully"
        }
    except Exception as e:
        logger.error(f"Error continuing workflow: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/projects/{project_id}", tags=["Projects"])
async def delete_project(project_id: str):
    """Delete a project"""
    try:
        success = await ppt_service.project_manager.delete_project(
            project_id=project_id,
            user_id=ANONYMOUS_USER_ID
        )
        return {
            "success": success,
            "message": "Project deleted successfully" if success else "Project deletion failed"
        }
    except Exception as e:
        logger.error(f"Error deleting project: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Template Selection
# ============================================================================

@app.post("/projects/{project_id}/select-template", tags=["Templates"])
async def select_template(project_id: str, request: TemplateSelectionRequest):
    """Select template for project"""
    try:
        result = await ppt_service.template_selection.select_template(
            project_id=project_id,
            template_id=request.template_id,
            template_type=request.template_type,
            custom_style=request.custom_style
        )
        return {
            "success": True,
            "data": result,
            "message": "Template selected successfully"
        }
    except Exception as e:
        logger.error(f"Error selecting template: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Slide Generation
# ============================================================================

@app.post("/projects/{project_id}/generate-slides", tags=["Slides"])
async def generate_slides(project_id: str):
    """Generate all slides for the project"""
    try:
        result = await ppt_service.generate_slides_from_project(project_id)
        return {
            "success": True,
            "data": result,
            "message": "Slides generated successfully"
        }
    except Exception as e:
        logger.error(f"Error generating slides: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{project_id}/slides/{slide_index}/regenerate", tags=["Slides"])
async def regenerate_slide(project_id: str, slide_index: int):
    """Regenerate a specific slide"""
    try:
        result = await ppt_service.regenerate_slide(project_id, slide_index)
        return {
            "success": True,
            "data": result,
            "message": "Slide regenerated successfully"
        }
    except Exception as e:
        logger.error(f"Error regenerating slide: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Export Functions
# ============================================================================

@app.get("/projects/{project_id}/export/html", tags=["Export"])
async def export_html(project_id: str):
    """Export project as HTML"""
    try:
        project = await ppt_service.project_manager.get_project(
            project_id,
            user_id=ANONYMOUS_USER_ID
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        html_content = project.slides_html or ""
        return HTMLResponse(content=html_content)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting HTML: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{project_id}/export/pdf", tags=["Export"])
async def export_pdf(project_id: str):
    """Export project as PDF"""
    try:
        pdf_path = await ppt_service.export_to_pdf(project_id)
        return FileResponse(
            path=pdf_path,
            filename=f"{project_id}.pdf",
            media_type="application/pdf"
        )
    except Exception as e:
        logger.error(f"Error exporting PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{project_id}/export/pptx", tags=["Export"])
async def export_pptx(project_id: str):
    """Export project as PPTX"""
    try:
        pptx_path = await ppt_service.export_to_pptx(project_id)
        return FileResponse(
            path=pptx_path,
            filename=f"{project_id}.pptx",
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
    except Exception as e:
        logger.error(f"Error exporting PPTX: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Research Functions
# ============================================================================

@app.get("/research/status", tags=["Research"])
async def get_research_status():
    """Check if research service is available"""
    try:
        research_service = getattr(ppt_service, 'research_service', None)
        available = research_service is not None and research_service.is_available()
        return {
            "available": available,
            "provider": ai_config.research_provider,
            "message": "Research service is available" if available else "Research service not configured"
        }
    except Exception as e:
        logger.error(f"Error checking research status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/research/conduct", tags=["Research"])
async def conduct_research(topic: str, max_results: int = 10):
    """Conduct web research on a topic"""
    try:
        if not ppt_service.research_service:
            raise HTTPException(status_code=400, detail="Research service not available")

        report = await ppt_service.research_service.conduct_research(
            topic=topic,
            max_results=max_results
        )
        return {
            "success": True,
            "data": report,
            "message": "Research completed successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error conducting research: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# AI Provider Configuration
# ============================================================================

@app.get("/ai/providers", tags=["AI Configuration"])
async def get_ai_providers():
    """Get available AI providers"""
    all_providers = ai_config.get_available_providers()
    return {
        "default_provider": ai_config.default_ai_provider,
        "available_providers": all_providers,
        "provider_status": {
            provider: ai_config.is_provider_available(provider)
            for provider in all_providers
        }
    }


# ============================================================================
# One-Shot Full PPT Generation
# ============================================================================

@app.post("/generate", tags=["Quick Generation"])
async def generate_full_ppt(request: PPTGenerationRequest):
    """One-shot full PPT generation: outline -> slides -> return HTML"""
    try:
        request.user_id = ANONYMOUS_USER_ID

        # Step 1: Create project
        project = await ppt_service.create_project_with_workflow(request)
        project_id = project.project_id

        # Step 2: Prepare confirmed requirements
        confirmed_requirements = {
            "topic": request.topic,
            "scenario": request.scenario,
            "requirements": request.requirements or "",
            "language": request.language or "zh",
            "target_audience": request.target_audience or "",
            "style": request.ppt_style or "general",
            "custom_style_prompt": request.custom_style_prompt or ""
        }

        # Step 3: Confirm requirements and update workflow
        await ppt_service.confirm_requirements_and_update_workflow(
            project_id,
            confirmed_requirements
        )

        # Step 4: Run all workflow stages sequentially
        stages_to_run = ["requirements_confirm", "outline_generation", "creative_design",
                          "template_selection", "slide_generation", "layout_repair"]

        for stage_id in stages_to_run:
            logger.info(f"Running workflow stage: {stage_id}")
            await ppt_service.start_workflow_from_stage(project_id, stage_id)

        # Step 5: Get final project
        final_project = await ppt_service.project_manager.get_project(
            project_id,
            user_id=ANONYMOUS_USER_ID
        )

        return {
            "success": True,
            "project_id": final_project.project_id,
            "title": final_project.title,
            "slides_html": final_project.slides_html,
            "message": "PPT generated successfully"
        }
    except Exception as e:
        logger.error(f"Error generating full PPT: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Run Server
# ============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "src.landppt.main_api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
