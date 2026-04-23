#!/usr/bin/env python3
"""
LandPPT API Test Script
Comprehensive testing for all API endpoints
"""

import requests
import json
import time
import sys
from typing import Dict, Any

API_BASE_URL = "http://localhost:8000"


def print_section(title: str):
    """Print a section header"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(success: bool, message: str, data: Any = None):
    """Print test result"""
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status}: {message}")
    if data:
        print(f"   Data: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}...")


def test_health():
    """Test health check endpoint"""
    print_section("Testing Health Check")
    try:
        response = requests.get(f"{API_BASE_URL}/health")
        response.raise_for_status()
        data = response.json()
        print_result(True, "Health check passed", data)
        return True
    except Exception as e:
        print_result(False, f"Health check failed: {e}")
        return False


def test_get_scenarios():
    """Test getting scenarios"""
    print_section("Testing Get Scenarios")
    try:
        response = requests.get(f"{API_BASE_URL}/scenarios")
        response.raise_for_status()
        data = response.json()
        print_result(True, f"Got {len(data)} scenarios", {"count": len(data)})
        return True
    except Exception as e:
        print_result(False, f"Get scenarios failed: {e}")
        return False


def test_get_ai_providers():
    """Test getting AI providers"""
    print_section("Testing Get AI Providers")
    try:
        response = requests.get(f"{API_BASE_URL}/ai/providers")
        response.raise_for_status()
        data = response.json()
        print_result(True, f"Default provider: {data.get('default_provider')}", data)
        return True
    except Exception as e:
        print_result(False, f"Get AI providers failed: {e}")
        return False


def test_generate_outline():
    """Test outline generation"""
    print_section("Testing Outline Generation")
    try:
        request_data = {
            "scenario": "technology",
            "topic": "人工智能在教育领域的应用",
            "requirements": "包含5-8页内容，重点介绍AI在个性化学习中的应用",
            "language": "zh"
        }
        response = requests.post(
            f"{API_BASE_URL}/outline/generate",
            json=request_data,
            timeout=120
        )
        response.raise_for_status()
        data = response.json()
        print_result(True, "Outline generated successfully", {
            "success": data.get("success"),
            "has_outline": data.get("outline") is not None
        })
        return True
    except Exception as e:
        print_result(False, f"Outline generation failed: {e}")
        return False


def test_create_project():
    """Test creating a project"""
    print_section("Testing Create Project")
    try:
        request_data = {
            "scenario": "business",
            "topic": "2024年度产品战略规划",
            "requirements": "重点介绍产品线规划和市场策略",
            "language": "zh"
        }
        response = requests.post(
            f"{API_BASE_URL}/projects",
            json=request_data,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        project_id = data.get("project_id")
        print_result(True, f"Project created: {project_id}", {
            "project_id": project_id,
            "title": data.get("title")
        })
        return project_id
    except Exception as e:
        print_result(False, f"Create project failed: {e}")
        return None


def test_list_projects():
    """Test listing projects"""
    print_section("Testing List Projects")
    try:
        response = requests.get(f"{API_BASE_URL}/projects?page=1&page_size=10")
        response.raise_for_status()
        data = response.json()
        print_result(True, f"Listed {len(data.get('projects', []))} projects", {
            "total": data.get("total"),
            "page": data.get("page")
        })
        return True
    except Exception as e:
        print_result(False, f"List projects failed: {e}")
        return False


def test_get_project(project_id: str):
    """Test getting a specific project"""
    print_section(f"Testing Get Project: {project_id}")
    try:
        response = requests.get(f"{API_BASE_URL}/projects/{project_id}")
        response.raise_for_status()
        data = response.json()
        print_result(True, f"Got project details", {
            "project_id": data.get("project_id"),
            "status": data.get("status")
        })
        return True
    except Exception as e:
        print_result(False, f"Get project failed: {e}")
        return False


def test_get_project_todo(project_id: str):
    """Test getting project todo board"""
    print_section(f"Testing Get Project Todo Board: {project_id}")
    try:
        response = requests.get(f"{API_BASE_URL}/projects/{project_id}/todo")
        response.raise_for_status()
        data = response.json()
        print_result(True, f"Got todo board", {
            "task_id": data.get("task_id"),
            "stages_count": len(data.get("stages", []))
        })
        return True
    except Exception as e:
        print_result(False, f"Get todo board failed: {e}")
        return False


def test_quick_generation():
    """Test one-shot full generation"""
    print_section("Testing One-Shot Full Generation")
    try:
        request_data = {
            "scenario": "general",
            "topic": "Python编程语言入门指南",
            "requirements": "适合初学者，包含基础语法和示例",
            "language": "zh"
        }
        print("   This may take 1-2 minutes...")
        response = requests.post(
            f"{API_BASE_URL}/generate",
            json=request_data,
            timeout=180
        )
        response.raise_for_status()
        data = response.json()
        print_result(True, "Full PPT generated successfully", {
            "project_id": data.get("project_id"),
            "has_html": data.get("slides_html") is not None
        })
        return data.get("project_id")
    except Exception as e:
        print_result(False, f"Full generation failed: {e}")
        return None


def test_export_html(project_id: str):
    """Test HTML export"""
    print_section(f"Testing HTML Export: {project_id}")
    try:
        response = requests.get(f"{API_BASE_URL}/projects/{project_id}/export/html")
        response.raise_for_status()
        html_content = response.text
        print_result(True, "HTML exported successfully", {
            "content_length": len(html_content),
            "has_html_tags": "<html" in html_content.lower() or "<div" in html_content.lower()
        })
        return True
    except Exception as e:
        print_result(False, f"HTML export failed: {e}")
        return False


def test_research_status():
    """Test research status"""
    print_section("Testing Research Status")
    try:
        response = requests.get(f"{API_BASE_URL}/research/status")
        response.raise_for_status()
        data = response.json()
        print_result(True, "Got research status", data)
        return True
    except Exception as e:
        print_result(False, f"Research status check failed: {e}")
        return False


def run_all_tests():
    """Run all API tests"""
    print("\n" + "%" * 60)
    print("%" + " " * 58 + "%")
    print("%" + " " * 15 + "LandPPT API Test Suite" + " " * 19 + "%")
    print("%" + " " * 58 + "%")
    print("%" * 60)

    results = []

    # Basic tests
    results.append(("health", test_health()))
    results.append(("scenarios", test_get_scenarios()))
    results.append(("ai_providers", test_get_ai_providers()))
    results.append(("outline", test_generate_outline()))
    results.append(("research_status", test_research_status()))

    # Project tests
    project_id = test_create_project()
    if project_id:
        results.append(("create_project", True))
        results.append(("list_projects", test_list_projects()))
        results.append(("get_project", test_get_project(project_id)))
        results.append(("get_todo", test_get_project_todo(project_id)))
    else:
        results.append(("create_project", False))

    # Full generation test (may take time)
    print_section("Optional: Full Generation Test")
    print("   Note: This test takes several minutes to complete.")
    print("   Run 'python test_api.py full' to enable this test.")

    # Summary
    print("\n" + "=" * 60)
    print("  TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {test_name}")

    print(f"\n  Total: {passed}/{total} tests passed")
    print(f"  Success rate: {passed/total*100:.1f}%")

    if passed == total:
        print("\n  🎉 All tests passed! API is working correctly.")
    else:
        print(f"\n  ⚠️  {total - passed} test(s) failed. Please check the errors above.")

    return passed == total


def run_specific_test(test_name: str):
    """Run a specific test"""
    tests = {
        "health": test_health,
        "scenarios": test_get_scenarios,
        "providers": test_get_ai_providers,
        "outline": test_generate_outline,
        "project": test_create_project,
        "projects": test_list_projects,
        "research": test_research_status,
        "full": test_quick_generation,
    }

    if test_name in tests:
        result = tests[test_name]()
        if isinstance(result, str):  # project_id
            print(f"\n  Project ID: {result}")
            test_get_project(result)
            test_export_html(result)
    else:
        print(f"Unknown test: {test_name}")
        print(f"Available tests: {', '.join(tests.keys())}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_specific_test(sys.argv[1])
    else:
        success = run_all_tests()
        sys.exit(0 if success else 1)
