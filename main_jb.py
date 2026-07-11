"""
学生智能助手 Agent 入口
直接运行根目录 main.py → http://localhost:8000
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("student_agent.main_jb:app", host="0.0.0.0", port=8000)
