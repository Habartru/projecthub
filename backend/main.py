#!/usr/bin/env python3
"""
ProjectHub Backend - API для управления проектами
"""

import os
import re
import json
import shlex
import logging
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import docker

logger = logging.getLogger(__name__)

# Конфигурация
PROJECTS_ROOT = Path.home() / "Projects"
PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
DB_PATH = PROJECTS_ROOT / ".projecthub.db"

# Brain / Knowledge base
BRAIN_DIR = Path.home() / "Projects" / "@memory" / "brain"
BRAIN_DAILY = BRAIN_DIR / "daily"
BRAIN_PROJECTS = BRAIN_DIR / "knowledge" / "projects"
BRAIN_INDEX = BRAIN_DIR / "knowledge" / "index.md"

# Модели данных
class Project(BaseModel):
    id: Optional[int] = None
    name: str
    path: str
    category: str
    display_name: str
    description: str = ""
    status: str = "active"
    tags: List[str] = []
    project_type: str = ""
    last_opened: Optional[str] = None
    open_count: int = 0
    label: Optional[str] = None  # favorite, working, archive
    sort_order: int = 0  # для custom сортировки

class Note(BaseModel):
    id: Optional[int] = None
    project_id: int
    content: str
    created_at: Optional[str] = None

class Command(BaseModel):
    id: Optional[int] = None
    project_id: int
    name: str
    command: str
    cwd: Optional[str] = None

class SettingValue(BaseModel):
    value: str
    type: str = "string"
    category: str = "general"

# Инициализация БД
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            path TEXT NOT NULL,
            category TEXT NOT NULL,
            display_name TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            tags TEXT DEFAULT '[]',
            project_type TEXT DEFAULT '',
            label TEXT DEFAULT NULL,
            sort_order INTEGER DEFAULT 0,
            last_opened TIMESTAMP,
            open_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            command TEXT NOT NULL,
            cwd TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
    ''')
    
    # Таблица настроек пользователя
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default',
            key TEXT NOT NULL,
            value TEXT,
            value_type TEXT DEFAULT 'string',
            category TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, key)
        )
    ''')
    
    # Таблица конфигураций редакторов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS editor_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default',
            editor_id TEXT NOT NULL,
            name TEXT NOT NULL,
            command TEXT NOT NULL,
            args_template TEXT DEFAULT '{path}',
            icon_path TEXT,
            color TEXT DEFAULT '#1f6feb',
            sort_order INTEGER DEFAULT 0,
            is_enabled BOOLEAN DEFAULT 1,
            is_default BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, editor_id)
        )
    ''')
    
    # Таблица переводов (локализация)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS translations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lang_code TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            context TEXT,
            UNIQUE(lang_code, key)
        )
    ''')

    # Таблица категорий
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            icon TEXT DEFAULT 'folder',
            color TEXT DEFAULT '#6e7681',
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Инициализация дефолтных редакторов
    init_default_editors(cursor)

    # Инициализация переводов
    init_translations(cursor)

    # Инициализация категорий из файловой системы
    init_categories(cursor)
    
    conn.commit()
    conn.close()

def init_default_editors(cursor):
    """Инициализация дефолтных редакторов если их нет"""
    default_editors = [
        ('windsurf', 'Windsurf', 'windsurf', '{path}', '/static/icons/windsurf.png', '#10b981', 0, 1, 1),
        ('vscode', 'VS Code', 'code', '--folder-uri {path}', '/static/icons/vscode.png', '#0078d4', 1, 1, 0),
        ('cursor', 'Cursor', 'cursor', '{path}', '/static/icons/cursor.png', '#f97316', 2, 1, 0),
        ('antigravity', 'Antigravity', 'antigravity', '{path}', '/static/icons/antigravity.png', '#8b5cf6', 3, 1, 0),
    ]
    
    for editor in default_editors:
        cursor.execute('''
            INSERT OR IGNORE INTO editor_configs 
            (user_id, editor_id, name, command, args_template, icon_path, color, sort_order, is_enabled, is_default)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', ('default',) + editor)

def init_translations(cursor):
    """Инициализация базовых переводов"""
    translations = [
        # Russian
        ('ru', 'app.name', 'ProjectHub', None),
        ('ru', 'app.tagline', 'Ваши проекты под контролем', None),
        ('ru', 'navigation.dashboard', 'Дашборд', None),
        ('ru', 'navigation.projects', 'Проекты', None),
        ('ru', 'navigation.settings', 'Настройки', None),
        ('ru', 'header.total', 'Всего', None),
        ('ru', 'header.active', 'Активных', None),
        ('ru', 'header.settings_tooltip', 'Настройки', None),
        ('ru', 'sidebar.categories', 'Категории', None),
        ('ru', 'sidebar.all_projects', 'Все проекты', None),
        ('ru', 'sidebar.active_projects', 'Активные', None),
        ('ru', 'sidebar.experiments', 'Эксперименты', None),
        ('ru', 'sidebar.games', 'Игры', None),
        ('ru', 'sidebar.archive', 'Архив', None),
        ('ru', 'sidebar.data', 'Данные', None),
        ('ru', 'sidebar.system', 'Система', None),
        ('ru', 'search.placeholder', 'Поиск проектов...', None),
        ('ru', 'sort.title', 'Сортировка', None),
        ('ru', 'sort.name', 'Имя', None),
        ('ru', 'sort.activity', 'Активность', None),
        ('ru', 'sort.status', 'Статус', None),
        ('ru', 'sort.favorite', 'Избранное', None),
        ('ru', 'sort.custom', 'Порядок', None),
        ('ru', 'projects.empty', 'Нет проектов', None),
        ('ru', 'projects.loading', 'Загрузка проектов...', None),
        ('ru', 'projects.sync', 'Синхронизировать', None),
        ('ru', 'projects.open_folder', 'Открыть папку', None),
        ('ru', 'system.cpu', 'CPU', None),
        ('ru', 'system.ram', 'RAM', None),
        ('ru', 'system.disk', 'Диск', None),
        ('ru', 'system.uptime', 'Время работы', None),
        ('ru', 'modal.close', 'Закрыть', None),
        ('ru', 'modal.info', 'Информация', None),
        ('ru', 'modal.path', 'Путь', None),
        ('ru', 'modal.type', 'Тип', None),
        ('ru', 'modal.status', 'Статус', None),
        ('ru', 'modal.label', 'Лейбл', None),
        ('ru', 'modal.labels', 'Лейблы', None),
        ('ru', 'modal.labels_favorite', 'Избранное', None),
        ('ru', 'modal.labels_working', 'В работе', None),
        ('ru', 'modal.labels_archive', 'Архив', None),
        ('ru', 'modal.labels_none', 'Нет', None),
        ('ru', 'modal.git', 'Git', None),
        ('ru', 'modal.git_branch', 'Ветка', None),
        ('ru', 'modal.git_changes', 'Изменений', None),
        ('ru', 'modal.git_last_commit', 'Последний коммит', None),
        ('ru', 'modal.docker', 'Docker', None),
        ('ru', 'modal.notes', 'Заметки', None),
        ('ru', 'modal.notes_empty', 'Нет заметок', None),
        ('ru', 'modal.notes_placeholder', 'Добавить заметку...', None),
        ('ru', 'modal.notes_add', 'Добавить', None),
        ('ru', 'modal.quick_actions', 'Быстрые действия', None),
        ('ru', 'projects.loading_error', 'Ошибка загрузки', None),
        ('ru', 'settings.title', 'Настройки', None),
        ('ru', 'settings.sections.general', 'Общие', None),
        ('ru', 'settings.sections.general_description', 'Основные настройки приложения', None),
        ('ru', 'settings.sections.appearance', 'Внешний вид', None),
        ('ru', 'settings.sections.editors', 'Редакторы', None),
        ('ru', 'settings.language.title', 'Язык интерфейса', None),
        ('ru', 'settings.language.description', 'Выберите предпочитаемый язык', None),
        ('ru', 'settings.theme.title', 'Тема оформления', None),
        ('ru', 'settings.theme.description', 'Выберите цветовую схему интерфейса', None),
        ('ru', 'settings.editors.title', 'Редакторы кода', None),
        ('ru', 'settings.editors.description', 'Настройте IDE и редакторы для открытия проектов', None),
        ('ru', 'settings.editors.default', 'По умолчанию', None),
        ('ru', 'settings.editors.enabled', 'Включен', None),
        ('ru', 'settings.editors.command', 'Команда', None),
        ('ru', 'settings.editors.test', 'Тест', None),
        ('ru', 'settings.editors.add', 'Добавить редактор', None),
        ('ru', 'settings.editors.empty', 'Нет настроенных редакторов', None),
        ('ru', 'settings.editors.name', 'Название', None),
        ('ru', 'settings.editors.args', 'Аргументы', None),
        ('ru', 'settings.editors.args_help', 'Используйте {path} для подстановки пути к проекту', None),
        ('ru', 'settings.editors.color', 'Цвет кнопки', None),
        ('ru', 'actions.save', 'Сохранить', None),
        ('ru', 'actions.reset', 'Сбросить', None),
        ('ru', 'actions.cancel', 'Отмена', None),
        ('ru', 'actions.edit', 'Редактировать', None),
        ('ru', 'actions.delete', 'Удалить', None),
        ('ru', 'toast.saved', 'Сохранено', None),
        ('ru', 'toast.error', 'Ошибка', None),
        ('ru', 'toast.editor_enabled', 'Редактор включен', None),
        ('ru', 'toast.editor_disabled', 'Редактор отключен', None),
        ('ru', 'toast.editor_default', 'Редактор по умолчанию изменен', None),
        ('ru', 'toast.editor_deleted', 'Редактор удален', None),
        ('ru', 'toast.fill_required', 'Заполните все обязательные поля', None),
        ('ru', 'toast.error_save', 'Ошибка сохранения', None),
        ('ru', 'toast.error_delete', 'Ошибка удаления', None),
        ('ru', 'confirm.delete_editor', 'Удалить этот редактор?', None),
        ('ru', 'settings.editors.configured', 'Настроенные редакторы', None),
        ('ru', 'settings.editors.disabled', 'Отключен', None),
        ('ru', 'settings.editors.name_placeholder', 'Например: VS Code', None),
        ('ru', 'settings.editors.command_placeholder', 'Например: code', None),
        
        # English
        ('en', 'app.name', 'ProjectHub', None),
        ('en', 'app.tagline', 'Your projects under control', None),
        ('en', 'navigation.dashboard', 'Dashboard', None),
        ('en', 'navigation.projects', 'Projects', None),
        ('en', 'navigation.settings', 'Settings', None),
        ('en', 'header.total', 'Total', None),
        ('en', 'header.active', 'Active', None),
        ('en', 'header.settings_tooltip', 'Settings', None),
        ('en', 'sidebar.categories', 'Categories', None),
        ('en', 'sidebar.all_projects', 'All Projects', None),
        ('en', 'sidebar.active_projects', 'Active', None),
        ('en', 'sidebar.experiments', 'Experiments', None),
        ('en', 'sidebar.games', 'Games', None),
        ('en', 'sidebar.archive', 'Archive', None),
        ('en', 'sidebar.data', 'Data', None),
        ('en', 'sidebar.system', 'System', None),
        ('en', 'search.placeholder', 'Search projects...', None),
        ('en', 'sort.title', 'Sort', None),
        ('en', 'sort.name', 'Name', None),
        ('en', 'sort.activity', 'Activity', None),
        ('en', 'sort.status', 'Status', None),
        ('en', 'sort.favorite', 'Favorite', None),
        ('en', 'sort.custom', 'Order', None),
        ('en', 'projects.empty', 'No projects', None),
        ('en', 'projects.loading', 'Loading projects...', None),
        ('en', 'projects.sync', 'Synchronize', None),
        ('en', 'projects.open_folder', 'Open Folder', None),
        ('en', 'system.cpu', 'CPU', None),
        ('en', 'system.ram', 'RAM', None),
        ('en', 'system.disk', 'Disk', None),
        ('en', 'system.uptime', 'Uptime', None),
        ('en', 'modal.close', 'Close', None),
        ('en', 'modal.info', 'Information', None),
        ('en', 'modal.path', 'Path', None),
        ('en', 'modal.type', 'Type', None),
        ('en', 'modal.status', 'Status', None),
        ('en', 'modal.label', 'Label', None),
        ('en', 'modal.labels', 'Labels', None),
        ('en', 'modal.labels_favorite', 'Favorite', None),
        ('en', 'modal.labels_working', 'Working', None),
        ('en', 'modal.labels_archive', 'Archive', None),
        ('en', 'modal.labels_none', 'None', None),
        ('en', 'modal.git', 'Git', None),
        ('en', 'modal.git_branch', 'Branch', None),
        ('en', 'modal.git_changes', 'Changes', None),
        ('en', 'modal.git_last_commit', 'Last Commit', None),
        ('en', 'modal.docker', 'Docker', None),
        ('en', 'modal.notes', 'Notes', None),
        ('en', 'modal.notes_empty', 'No notes', None),
        ('en', 'modal.notes_placeholder', 'Add note...', None),
        ('en', 'modal.notes_add', 'Add', None),
        ('en', 'modal.quick_actions', 'Quick Actions', None),
        ('en', 'projects.loading_error', 'Loading error', None),
        ('en', 'settings.title', 'Settings', None),
        ('en', 'settings.sections.general', 'General', None),
        ('en', 'settings.sections.general_description', 'Basic application settings', None),
        ('en', 'settings.sections.appearance', 'Appearance', None),
        ('en', 'settings.sections.editors', 'Editors', None),
        ('en', 'settings.language.title', 'Interface Language', None),
        ('en', 'settings.language.description', 'Select your preferred language', None),
        ('en', 'settings.theme.title', 'Theme', None),
        ('en', 'settings.theme.description', 'Select UI color scheme', None),
        ('en', 'settings.editors.title', 'Code Editors', None),
        ('en', 'settings.editors.description', 'Configure your IDEs and editors for opening projects', None),
        ('en', 'settings.editors.default', 'Default', None),
        ('en', 'settings.editors.enabled', 'Enabled', None),
        ('en', 'settings.editors.command', 'Command', None),
        ('en', 'settings.editors.test', 'Test', None),
        ('en', 'settings.editors.add', 'Add Editor', None),
        ('en', 'settings.editors.empty', 'No configured editors', None),
        ('en', 'settings.editors.name', 'Name', None),
        ('en', 'settings.editors.args', 'Arguments', None),
        ('en', 'settings.editors.args_help', 'Use {path} to substitute project path', None),
        ('en', 'settings.editors.color', 'Button Color', None),
        ('en', 'actions.save', 'Save', None),
        ('en', 'actions.reset', 'Reset', None),
        ('en', 'actions.cancel', 'Cancel', None),
        ('en', 'actions.edit', 'Edit', None),
        ('en', 'actions.delete', 'Delete', None),
        ('en', 'toast.saved', 'Saved', None),
        ('en', 'toast.error', 'Error', None),
        ('en', 'toast.editor_enabled', 'Editor enabled', None),
        ('en', 'toast.editor_disabled', 'Editor disabled', None),
        ('en', 'toast.editor_default', 'Default editor changed', None),
        ('en', 'toast.editor_deleted', 'Editor deleted', None),
        ('en', 'toast.fill_required', 'Fill in all required fields', None),
        ('en', 'toast.error_save', 'Error saving', None),
        ('en', 'toast.error_delete', 'Error deleting', None),
        ('en', 'confirm.delete_editor', 'Delete this editor?', None),
        ('en', 'settings.editors.configured', 'Configured editors', None),
        ('en', 'settings.editors.disabled', 'Disabled', None),
        ('en', 'settings.editors.name_placeholder', 'e.g. VS Code', None),
        ('en', 'settings.editors.command_placeholder', 'e.g. code', None),
        
        # Chinese (Simplified)
        ('zh', 'app.name', 'ProjectHub', None),
        ('zh', 'app.tagline', '您的项目在掌控中', None),
        ('zh', 'navigation.dashboard', '仪表盘', None),
        ('zh', 'navigation.projects', '项目', None),
        ('zh', 'navigation.settings', '设置', None),
        ('zh', 'header.total', '总计', None),
        ('zh', 'header.active', '活跃', None),
        ('zh', 'header.settings_tooltip', '设置', None),
        ('zh', 'sidebar.categories', '分类', None),
        ('zh', 'sidebar.all_projects', '所有项目', None),
        ('zh', 'sidebar.active_projects', '活跃的', None),
        ('zh', 'sidebar.experiments', '实验', None),
        ('zh', 'sidebar.games', '游戏', None),
        ('zh', 'sidebar.archive', '归档', None),
        ('zh', 'sidebar.data', '数据', None),
        ('zh', 'sidebar.system', '系统', None),
        ('zh', 'search.placeholder', '搜索项目...', None),
        ('zh', 'sort.title', '排序', None),
        ('zh', 'sort.name', '名称', None),
        ('zh', 'sort.activity', '活跃度', None),
        ('zh', 'sort.status', '状态', None),
        ('zh', 'sort.favorite', '收藏', None),
        ('zh', 'sort.custom', '顺序', None),
        ('zh', 'projects.empty', '没有项目', None),
        ('zh', 'projects.loading', '加载项目中...', None),
        ('zh', 'projects.sync', '同步', None),
        ('zh', 'projects.open_folder', '打开文件夹', None),
        ('zh', 'system.cpu', 'CPU', None),
        ('zh', 'system.ram', '内存', None),
        ('zh', 'system.disk', '磁盘', None),
        ('zh', 'system.uptime', '运行时间', None),
        ('zh', 'modal.close', '关闭', None),
        ('zh', 'modal.info', '信息', None),
        ('zh', 'modal.path', '路径', None),
        ('zh', 'modal.type', '类型', None),
        ('zh', 'modal.status', '状态', None),
        ('zh', 'modal.label', '标签', None),
        ('zh', 'modal.labels', '标签', None),
        ('zh', 'modal.labels_favorite', '收藏', None),
        ('zh', 'modal.labels_working', '进行中', None),
        ('zh', 'modal.labels_archive', '归档', None),
        ('zh', 'modal.labels_none', '无', None),
        ('zh', 'modal.git', 'Git', None),
        ('zh', 'modal.git_branch', '分支', None),
        ('zh', 'modal.git_changes', '更改', None),
        ('zh', 'modal.git_last_commit', '最后提交', None),
        ('zh', 'modal.docker', 'Docker', None),
        ('zh', 'modal.notes', '笔记', None),
        ('zh', 'modal.notes_empty', '没有笔记', None),
        ('zh', 'modal.notes_placeholder', '添加笔记...', None),
        ('zh', 'modal.notes_add', '添加', None),
        ('zh', 'modal.quick_actions', '快速操作', None),
        ('zh', 'projects.loading_error', '加载错误', None),
        ('zh', 'settings.title', '设置', None),
        ('zh', 'settings.sections.general', '常规', None),
        ('zh', 'settings.sections.general_description', '基本应用程序设置', None),
        ('zh', 'settings.sections.appearance', '外观', None),
        ('zh', 'settings.sections.editors', '编辑器', None),
        ('zh', 'settings.language.title', '界面语言', None),
        ('zh', 'settings.language.description', '选择您偏好的语言', None),
        ('zh', 'settings.theme.title', '主题', None),
        ('zh', 'settings.theme.description', '选择界面配色方案', None),
        ('zh', 'settings.editors.title', '代码编辑器', None),
        ('zh', 'settings.editors.description', '配置您的 IDE 和编辑器', None),
        ('zh', 'settings.editors.default', '默认', None),
        ('zh', 'settings.editors.enabled', '已启用', None),
        ('zh', 'settings.editors.command', '命令', None),
        ('zh', 'settings.editors.test', '测试', None),
        ('zh', 'settings.editors.add', '添加编辑器', None),
        ('zh', 'settings.editors.empty', '没有配置的编辑器', None),
        ('zh', 'settings.editors.configured', '已配置的编辑器', None),
        ('zh', 'settings.editors.disabled', '已禁用', None),
        ('zh', 'settings.editors.name', '名称', None),
        ('zh', 'settings.editors.name_placeholder', '例如 VS Code', None),
        ('zh', 'settings.editors.command_placeholder', '例如 code', None),
        ('zh', 'settings.editors.args', '参数', None),
        ('zh', 'settings.editors.args_help', '使用 {path} 替换项目路径', None),
        ('zh', 'settings.editors.color', '按钮颜色', None),
        ('zh', 'actions.save', '保存', None),
        ('zh', 'actions.reset', '重置', None),
        ('zh', 'actions.cancel', '取消', None),
        ('zh', 'actions.edit', '编辑', None),
        ('zh', 'actions.delete', '删除', None),
        ('zh', 'toast.saved', '已保存', None),
        ('zh', 'toast.error', '错误', None),
        ('zh', 'toast.editor_enabled', '编辑器已启用', None),
        ('zh', 'toast.editor_disabled', '编辑器已禁用', None),
        ('zh', 'toast.editor_default', '默认编辑器已更改', None),
        ('zh', 'toast.editor_deleted', '编辑器已删除', None),
        ('zh', 'toast.fill_required', '请填写所有必填字段', None),
        ('zh', 'toast.error_save', '保存错误', None),
        ('zh', 'toast.error_delete', '删除错误', None),
        ('zh', 'confirm.delete_editor', '删除此编辑器？', None),
    ]
    
    for trans in translations:
        cursor.execute('''
            INSERT OR IGNORE INTO translations (lang_code, key, value, context)
            VALUES (?, ?, ?, ?)
        ''', trans)

# Иконки и цвета для известных категорий
CATEGORY_PRESETS = {
    '@active': {'icon': 'circle-dot', 'color': '#3fb950', 'display_name': 'Активные'},
    '@bringo': {'icon': 'briefcase', 'color': '#3fb950', 'display_name': 'Bringo'},
    '@BLOC': {'icon': 'blocks', 'color': '#f0883e', 'display_name': 'BLOC'},
    '@games': {'icon': 'gamepad-2', 'color': '#a371f7', 'display_name': 'Игры'},
    '@infrastructure': {'icon': 'server', 'color': '#58a6ff', 'display_name': 'Инфраструктура'},
    '@site': {'icon': 'globe', 'color': '#58a6ff', 'display_name': 'Сайты'},
    '@teleleo': {'icon': 'radio', 'color': '#f97316', 'display_name': 'Teleleo'},
    '@docs': {'icon': 'file-text', 'color': '#8b949e', 'display_name': 'Документы'},
    '@ГОТОВЫЕ': {'icon': 'check-circle', 'color': '#3fb950', 'display_name': 'Готовые'},
    '@надо_доделать': {'icon': 'clock', 'color': '#f0883e', 'display_name': 'Надо доделать'},
}

def init_categories(cursor):
    """Инициализация категорий из файловой системы"""
    # Собираем все категории: @-папки + подкатегории (контейнеры)
    all_categories = set()

    for category_dir in PROJECTS_ROOT.iterdir():
        if not category_dir.is_dir() or not category_dir.name.startswith('@'):
            continue
        all_categories.add(category_dir.name)

        # Ищем контейнерные подпапки (используем ту же логику что scan_projects)
        for item_dir in category_dir.iterdir():
            if not item_dir.is_dir() or item_dir.name.startswith('.'):
                continue
            if _is_container_dir(item_dir):
                all_categories.add(item_dir.name)

    for idx, cat_name in enumerate(sorted(all_categories)):
        preset = CATEGORY_PRESETS.get(cat_name, {})
        display = preset.get('display_name', cat_name.lstrip('@').replace('_', ' '))
        icon = preset.get('icon', 'folder')
        color = preset.get('color', '#6e7681')

        cursor.execute('''
            INSERT OR IGNORE INTO categories (name, display_name, icon, color, sort_order)
            VALUES (?, ?, ?, ?, ?)
        ''', (cat_name, display, icon, color, idx))

PROJECT_MARKERS = {
    'package.json', 'requirements.txt', 'Cargo.toml', 'go.mod',
    'pom.xml', 'build.gradle', 'Makefile', 'CMakeLists.txt',
    'manage.py', 'setup.py', 'pyproject.toml',
}

def _is_project_dir(d: Path) -> bool:
    """Проверяет, является ли папка проектом (есть маркеры или .git)"""
    if (d / '.git').is_dir():
        return True
    for marker in PROJECT_MARKERS:
        if (d / marker).exists():
            return True
    return False

MONOREPO_PART_NAMES = {
    'frontend', 'backend', 'server', 'client', 'shared', 'app', 'api',
    'web', 'mobile', 'core', 'common', 'lib', 'libs', 'packages',
    'services', 'infra', 'deploy', 'scripts', 'tools', 'docs',
    'mcp-server', 'collector', 'animation', 'dev',
}

def _is_container_dir(d: Path) -> bool:
    """Проверяет, является ли папка контейнером (группой независимых проектов).
    Отличает от монорепо по трём признакам:
    1. Подпапки с именами frontend/backend/server/etc → монорепо
    2. Подпапки содержат имя родителя (vivoai-server в VIVOAI) → монорепо
    3. Независимые имена → контейнер"""
    if _is_project_dir(d):
        return False
    subdirs = [s for s in d.iterdir() if s.is_dir() and not s.name.startswith('.')]
    if not subdirs:
        return False
    project_subdirs = [s for s in subdirs if _is_project_dir(s)]
    if not project_subdirs:
        return False
    # Если большинство подпапок-проектов — типичные части монорепо → НЕ контейнер
    monorepo_count = sum(1 for s in project_subdirs if s.name.lower() in MONOREPO_PART_NAMES)
    if monorepo_count > len(project_subdirs) / 2:
        return False
    # Если подпапки содержат имя родителя → это варианты одного проекта, НЕ контейнер
    # (datalens, datalens-agent, datalens-mcp внутри DATALENS → монорепо)
    parent_name = d.name.lower()
    name_shared = sum(1 for s in project_subdirs
                      if parent_name in s.name.lower() or s.name.lower() in parent_name)
    if name_shared > len(project_subdirs) / 2:
        return False
    # Минимум 2 подпапки-проекта с независимыми именами → контейнер
    independent = len(project_subdirs) - name_shared
    return independent >= 2

def scan_projects():
    """Сканирование проектов с автодетектом контейнерных папок (глубина 2-3)"""
    projects = []

    for category_dir in PROJECTS_ROOT.iterdir():
        if not category_dir.is_dir() or not category_dir.name.startswith('@'):
            continue

        fs_category = category_dir.name  # @bringo, @active, etc.

        for item_dir in category_dir.iterdir():
            if not item_dir.is_dir() or item_dir.name.startswith('.'):
                continue

            if _is_container_dir(item_dir):
                # Это контейнер (чат, сбор данных, etc.) — сканируем подпапки
                subcategory = item_dir.name  # "чат", "сбор данных"
                for sub_project_dir in item_dir.iterdir():
                    if not sub_project_dir.is_dir() or sub_project_dir.name.startswith('.'):
                        continue
                    # Уникальное имя: "контейнер/проект" чтобы избежать коллизий
                    unique_name = f"{subcategory}/{sub_project_dir.name}"
                    project_type = detect_project_type(sub_project_dir)
                    projects.append({
                        "name": unique_name,
                        "path": str(sub_project_dir),
                        "category": subcategory,
                        "parent_category": fs_category,
                        "display_name": sub_project_dir.name.replace('_', ' ').replace('-', ' '),
                        "project_type": project_type,
                        "status": "active" if fs_category == "@active" else "archived"
                    })
            else:
                # Обычный проект
                project_type = detect_project_type(item_dir)
                projects.append({
                    "name": item_dir.name,
                    "path": str(item_dir),
                    "category": fs_category,
                    "parent_category": fs_category,
                    "display_name": item_dir.name.replace('_', ' ').replace('-', ' '),
                    "project_type": project_type,
                    "status": "active" if fs_category == "@active" else "archived"
                })

    return projects

def detect_project_type(project_dir: Path) -> str:
    """Улучшенное определение типа проекта с глубоким анализом"""
    
    # Получаем все файлы (рекурсивно, но ограничиваем глубину)
    all_files = []
    try:
        for item in project_dir.iterdir():
            if item.is_file():
                all_files.append(item.name)
            elif item.is_dir() and not item.name.startswith('.') and item.name not in ['node_modules', 'venv', '.git', '__pycache__', 'target', 'build', 'dist']:
                # Проверяем первый уровень подпапок
                try:
                    for subitem in item.iterdir():
                        if subitem.is_file():
                            all_files.append(f"{item.name}/{subitem.name}")
                except Exception:
                    logger.debug("Failed to iterate subdirectory in %s", project_dir)
    except Exception:
        logger.debug("Failed to iterate project directory %s", project_dir)
    
    files = set(all_files)
    
    # Node.js / TypeScript ecosystem
    if "package.json" in files or any("package.json" in f for f in files):
        # Проверяем фреймворки
        pkg_path = project_dir / "package.json"
        if pkg_path.exists():
            try:
                import json
                with open(pkg_path) as f:
                    pkg = json.load(f)
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    
                    if "next" in deps: return "nextjs"
                    if "react" in deps: 
                        if "react-native" in deps: return "react-native"
                        return "react"
                    if "vue" in deps: return "vue"
                    if "@angular/core" in deps: return "angular"
                    if "svelte" in deps: return "svelte"
                    if "express" in deps: return "express"
                    if "@nestjs/core" in deps: return "nestjs"
                    if "electron" in deps: return "electron"
            except Exception:
                logger.debug("Failed to parse package.json in %s", project_dir)
        
        # Проверяем config файлы
        if any(f.endswith("tsconfig.json") for f in files) or any(".ts" in f for f in files):
            return "typescript"
        return "nodejs"
    
    # Python ecosystem
    python_markers = ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile", "setup.cfg", "poetry.lock", " Pipfile.lock"]
    if any(m in files for m in python_markers) or any("requirements" in f for f in files):
        # Проверяем фреймворки
        for req_file in ["requirements.txt", "requirements-dev.txt", "requirements-prod.txt"]:
            req_path = project_dir / req_file
            if req_path.exists():
                try:
                    content = req_path.read_text().lower()
                    if "django" in content: return "django"
                    if "flask" in content: return "flask"
                    if "fastapi" in content: return "fastapi"
                except Exception:
                    logger.debug("Failed to read %s in %s", req_file, project_dir)

        pyproject = project_dir / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text().lower()
                if "django" in content: return "django"
                if "flask" in content: return "flask"
                if "fastapi" in content: return "fastapi"
            except Exception:
                logger.debug("Failed to read pyproject.toml in %s", project_dir)
        
        return "python"
    
    # Docker
    docker_files = ["docker-compose.yml", "docker-compose.yaml", "Dockerfile", "docker-compose.dev.yml", "docker-compose.prod.yml", ".dockerignore"]
    if any(d in files for d in docker_files) or any("Dockerfile" in f for f in files):
        return "docker"
    
    # Rust
    if "Cargo.toml" in files or any("Cargo" in f for f in files):
        return "rust"
    
    # Go
    if "go.mod" in files or "go.sum" in files or any("main.go" in f for f in files):
        return "go"
    
    # Java ecosystem
    if "pom.xml" in files:
        return "maven"
    if "build.gradle" in files or "build.gradle.kts" in files:
        # Проверяем если это Android
        if (project_dir / "app" / "build.gradle").exists() or (project_dir / "app" / "src" / "main").exists():
            return "android"
        return "gradle"
    
    # PHP ecosystem
    if "composer.json" in files or "composer.lock" in files:
        composer_path = project_dir / "composer.json"
        if composer_path.exists():
            try:
                import json
                with open(composer_path) as f:
                    pkg = json.load(f)
                    reqs = {**pkg.get("require", {}), **pkg.get("require-dev", {})}
                    if "laravel/framework" in reqs: return "laravel"
                    if "symfony/framework" in reqs: return "symfony"
            except Exception:
                logger.debug("Failed to parse composer.json in %s", project_dir)
        return "php"
    
    # Ruby
    if "Gemfile" in files or "Gemfile.lock" in files:
        return "ruby"
    if any(f.endswith(".gemspec") for f in files):
        return "ruby-gem"
    
    # Elixir
    if "mix.exs" in files or "mix.lock" in files:
        return "elixir"
    
    # Haskell
    if "stack.yaml" in files or "package.yaml" in files or "cabal.project" in files:
        return "haskell"
    
    # C/C++
    if "CMakeLists.txt" in files:
        return "cmake"
    if "Makefile" in files or "makefile" in files or "GNUmakefile" in files:
        return "make"
    if any(f.endswith(".pro") for f in files):  # Qt project
        return "qt"
    
    # .NET / C#
    if any(f.endswith(".csproj") for f in files) or any(f.endswith(".csproj") for f in all_files):
        return "csharp"
    if any(f.endswith(".sln") for f in files):
        return "dotnet"
    
    # Swift / iOS
    if "Package.swift" in files:
        return "swift"
    if "Podfile" in files or "Podfile.lock" in files:
        return "cocoapods"
    
    # Android
    if "build.gradle" in files:
        if (project_dir / "app" / "build.gradle").exists():
            return "android"
    
    # Kotlin
    if any(f.endswith(".kt") or f.endswith(".kts") for f in files):
        return "kotlin"
    
    # Lua
    if any(f.endswith(".rockspec") for f in files) or "main.lua" in files:
        return "lua"
    
    # Zig
    if "build.zig" in files or any(f.endswith(".zig") for f in files):
        return "zig"
    
    # Nim
    if any(f.endswith(".nimble") for f in files) or any(f.endswith(".nim") for f in files):
        return "nim"
    
    # Crystal
    if "shard.yml" in files or "shard.lock" in files:
        return "crystal"
    
    # Dart / Flutter
    if "pubspec.yaml" in files or "pubspec.lock" in files:
        if (project_dir / "lib" / "main.dart").exists() or (project_dir / "android").exists():
            return "flutter"
        return "dart"
    
    # R
    if "DESCRIPTION" in files or "NAMESPACE" in files:
        return "r"
    
    # Julia
    if "Project.toml" in files:
        return "julia"
    
    # Scala
    if "build.sbt" in files:
        return "scala"
    
    # Clojure
    if "project.clj" in files or "deps.edn" in files:
        return "clojure"
    
    # OCaml
    if any(f.endswith(".opam") for f in files) or "dune-project" in files:
        return "ocaml"
    
    # Shell/Bash
    if any(f in files for f in ["install.sh", "setup.sh", "run.sh", "build.sh"]):
        return "bash"
    
    # Terraform / Infrastructure
    if any(f.endswith(".tf") or f.endswith(".tfvars") for f in files):
        return "terraform"
    
    # Ansible
    if "ansible.cfg" in files or any("playbook" in f for f in files) or any("site.yml" in f for f in files):
        return "ansible"
    
    # Kubernetes
    if any(f in files for f in ["kustomization.yaml", "kustomization.yml", "Chart.yaml"]):
        return "k8s"
    
    # Hugo
    if "hugo.toml" in files or "config.toml" in files:
        if (project_dir / "content").exists() or (project_dir / "themes").exists():
            return "hugo"
    
    # Jekyll
    if "_config.yml" in files and (project_dir / "_posts").exists():
        return "jekyll"
    
    # Next.js
    if "next.config.js" in files or "next.config.mjs" in files or "next.config.ts" in files:
        return "nextjs"
    
    # Astro
    if "astro.config.mjs" in files or "astro.config.js" in files or "astro.config.ts" in files:
        return "astro"
    
    # Vite
    if "vite.config.js" in files or "vite.config.ts" in files:
        return "vite"
    
    # Webpack
    if "webpack.config.js" in files:
        return "webpack"
    
    # Rollup
    if "rollup.config.js" in files:
        return "rollup"
    
    # Parcel
    if ".parcelrc" in files:
        return "parcel"
    
    # Tauri
    if "tauri.conf.json" in files or "tauri.conf.json5" in files:
        return "tauri"
    
    # Capacitor / Ionic
    if "capacitor.config.json" in files or "capacitor.config.ts" in files:
        return "capacitor"
    
    # Unity
    if (project_dir / "Assets").exists() and (project_dir / "ProjectSettings").exists():
        return "unity"
    
    # Unreal Engine
    if any(f.endswith(".uproject") for f in files):
        return "unreal"
    
    # Godot
    if "project.godot" in files:
        return "godot"
    
    # Love2D
    if "main.lua" in files and (project_dir / "conf.lua").exists():
        return "love2d"
    
    # PICO-8
    if any(f.endswith(".p8") for f in files):
        return "pico8"
    
    # Check for extensions in all files
    ext_map = {
        '.py': 'python',
        '.js': 'nodejs',
        '.ts': 'typescript',
        '.tsx': 'react',
        '.jsx': 'react',
        '.vue': 'vue',
        '.svelte': 'svelte',
        '.rs': 'rust',
        '.go': 'go',
        '.java': 'java',
        '.kt': 'kotlin',
        '.kts': 'kotlin',
        '.rb': 'ruby',
        '.erb': 'ruby',
        '.php': 'php',
        '.swift': 'swift',
        '.scala': 'scala',
        '.sc': 'scala',
        '.clj': 'clojure',
        '.cljs': 'clojure',
        '.ex': 'elixir',
        '.exs': 'elixir',
        '.hs': 'haskell',
        '.lhs': 'haskell',
        '.nim': 'nim',
        '.zig': 'zig',
        '.cr': 'crystal',
        '.dart': 'dart',
        '.r': 'r',
        '.R': 'r',
        '.jl': 'julia',
        '.ml': 'ocaml',
        '.mli': 'ocaml',
        '.lua': 'lua',
        '.c': 'c',
        '.cpp': 'cpp',
        '.cc': 'cpp',
        '.cxx': 'cpp',
        '.h': 'c',
        '.hpp': 'cpp',
        '.cs': 'csharp',
        '.fs': 'dotnet',
        '.fsx': 'dotnet',
        '.vb': 'dotnet',
        '.sh': 'bash',
        '.bash': 'bash',
        '.zsh': 'bash',
        '.fish': 'bash',
        '.ps1': 'powershell',
        '.pl': 'perl',
        '.pm': 'perl',
        '.t': 'perl',
        '.pod': 'perl',
        '.gd': 'godot',
        '.tscn': 'godot',
    }
    
    for f in all_files:
        for ext, ptype in ext_map.items():
            if f.endswith(ext):
                return ptype
    
    return "unknown"

def sync_projects():
    """Синхронизация проектов с БД (с обновлением типов и удалением несуществующих)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    scanned = scan_projects()
    # Индекс по пути — самый надёжный уникальный ключ
    scanned_by_path = {proj["path"]: proj for proj in scanned}

    # Удаляем проекты, которых больше нет на диске
    cursor.execute("SELECT id, name, path FROM projects")
    existing_projects = cursor.fetchall()

    for proj_id, name, path in existing_projects:
        if path not in scanned_by_path or not os.path.exists(path):
            cursor.execute("DELETE FROM projects WHERE id = ?", (proj_id,))
            cursor.execute("DELETE FROM notes WHERE project_id = ?", (proj_id,))
            cursor.execute("DELETE FROM commands WHERE project_id = ?", (proj_id,))

    for proj in scanned:
        # Проверяем по пути (более надёжно чем по имени)
        cursor.execute("SELECT id, category FROM projects WHERE path = ?", (proj["path"],))
        existing = cursor.fetchone()

        if existing:
            proj_id, db_category = existing
            # Не перезаписываем категорию если пользователь её вручную менял
            was_auto = db_category in (proj.get("parent_category", proj["category"]), proj["category"])
            new_category = proj["category"] if was_auto else db_category
            cursor.execute('''
                UPDATE projects
                SET project_type = ?, name = ?, display_name = ?, status = ?, category = ?
                WHERE id = ?
            ''', (proj["project_type"], proj["name"],
                  proj["display_name"], proj["status"], new_category, proj_id))
        else:
            # Создаем новый проект
            cursor.execute('''
                INSERT INTO projects (name, path, category, display_name, project_type, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (proj["name"], proj["path"], proj["category"],
                  proj["display_name"], proj["project_type"], proj["status"]))

    # Обновляем категории
    init_categories(cursor)

    conn.commit()
    conn.close()

# FastAPI приложение
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    sync_projects()
    yield

app = FastAPI(title="ProjectHub", lifespan=lifespan)

# API Endpoints
@app.get("/api/projects")
def get_projects(
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort: Optional[str] = Query("name")  # name, activity, status, favorite, custom
):
    """Получить список проектов с сортировкой"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT * FROM projects WHERE 1=1"
    params = []
    
    if category:
        query += " AND category = ?"
        params.append(category)
    if status:
        query += " AND status = ?"
        params.append(status)
    if search:
        query += " AND (name LIKE ? OR display_name LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    
    # Сортировка
    if sort == "activity":
        query += " ORDER BY last_opened IS NULL, last_opened DESC, open_count DESC"
    elif sort == "status":
        # Сначала активные, потом архив
        query += " ORDER BY CASE WHEN status = 'active' THEN 0 ELSE 1 END, name"
    elif sort == "favorite":
        # Сначала избранные
        query += " ORDER BY CASE WHEN label = 'favorite' THEN 0 ELSE 1 END, open_count DESC"
    elif sort == "custom":
        query += " ORDER BY sort_order ASC, name ASC"
    else:
        # По умолчанию - по имени
        query += " ORDER BY name ASC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    projects = []
    for row in rows:
        proj = dict(row)
        proj["tags"] = json.loads(proj.get("tags", "[]"))
        projects.append(proj)
    
    return {"projects": projects, "total": len(projects), "sort": sort}

@app.post("/api/projects/sync")
def api_sync_projects():
    """Ручная синхронизация проектов с диском (добавляет новые, удаляет несуществующие)"""
    try:
        sync_projects()
        # Получаем статистику после синхронизации
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM projects")
        total = cursor.fetchone()[0]
        conn.close()
        return {"status": "synced", "total": total}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")

@app.get("/api/projects/live")
def get_live_projects():
    """Return project ids that have running Docker containers."""
    live_ids = []
    try:
        client = docker.from_env()
        running = {c.name.lower(): c for c in client.containers.list()}
        if not running:
            return {"live": []}
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM projects")
        for pid, name in cursor.fetchall():
            if any(name.lower() in cname for cname in running):
                live_ids.append(pid)
        conn.close()
    except Exception:
        pass
    return {"live": live_ids}

@app.get("/api/projects/{project_id}")
def get_project(project_id: int):
    """Получить детали проекта"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")
    
    project = dict(row)
    project["tags"] = json.loads(project.get("tags", "[]"))
    
    # Получить заметки
    cursor.execute("SELECT * FROM notes WHERE project_id = ? ORDER BY created_at DESC", (project_id,))
    project["notes"] = [dict(r) for r in cursor.fetchall()]
    
    conn.close()
    return project

@app.post("/api/projects/{project_id}/open")
def open_project(project_id: int):
    """Открыть проект (обновить статистику)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE projects 
        SET open_count = open_count + 1, last_opened = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (project_id,))
    
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.post("/api/projects/{project_id}/notes")
def add_note(project_id: int, note: Note):
    """Добавить заметку к проекту"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO notes (project_id, content) VALUES (?, ?)",
        (project_id, note.content)
    )
    
    note_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {"id": note_id, "status": "created"}

# ===== Categories API =====

class CategoryCreate(BaseModel):
    name: str
    display_name: str
    icon: str = "folder"
    color: str = "#6e7681"

class CategoryUpdate(BaseModel):
    display_name: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None

@app.get("/api/categories")
def get_categories():
    """Получить все категории с количеством проектов"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM categories ORDER BY sort_order, name")
    categories = [dict(row) for row in cursor.fetchall()]

    # Считаем проекты в каждой категории
    cursor.execute("SELECT category, COUNT(*) as cnt FROM projects GROUP BY category")
    counts = {row['category']: row['cnt'] for row in cursor.fetchall()}

    for cat in categories:
        cat['project_count'] = counts.get(cat['name'], 0)

    conn.close()
    return {"categories": categories}

@app.post("/api/categories")
def create_category(cat: CategoryCreate):
    """Создать новую категорию"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Получаем максимальный sort_order
    cursor.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM categories")
    next_order = cursor.fetchone()[0]

    try:
        cursor.execute('''
            INSERT INTO categories (name, display_name, icon, color, sort_order)
            VALUES (?, ?, ?, ?, ?)
        ''', (cat.name, cat.display_name, cat.icon, cat.color, next_order))
        cat_id = cursor.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail=f"Category '{cat.name}' already exists")

    conn.close()
    return {"id": cat_id, "status": "created"}

@app.put("/api/categories/{cat_id}")
def update_category(cat_id: int, cat: CategoryUpdate):
    """Обновить категорию"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    updates = []
    params = []
    if cat.display_name is not None:
        updates.append("display_name = ?")
        params.append(cat.display_name)
    if cat.icon is not None:
        updates.append("icon = ?")
        params.append(cat.icon)
    if cat.color is not None:
        updates.append("color = ?")
        params.append(cat.color)

    if not updates:
        conn.close()
        return {"status": "no_changes"}

    params.append(cat_id)
    cursor.execute(f"UPDATE categories SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return {"status": "updated"}

@app.delete("/api/categories/{cat_id}")
def delete_category(cat_id: int):
    """Удалить категорию (проекты не удаляются, только обнуляется привязка)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Получаем имя категории
    cursor.execute("SELECT name FROM categories WHERE id = ?", (cat_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Category not found")

    cat_name = row[0]

    # Проекты в этой категории получают parent_category (@ папку)
    # Не удаляем проекты — только категорию из справочника
    cursor.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "name": cat_name}

@app.post("/api/projects/{project_id}/category")
def set_project_category(project_id: int, data: dict):
    """Назначить категорию проекту"""
    category = data.get("category")
    if not category:
        raise HTTPException(status_code=400, detail="Category is required")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")

    cursor.execute("UPDATE projects SET category = ? WHERE id = ?", (category, project_id))
    conn.commit()
    conn.close()
    return {"status": "updated", "category": category}

@app.get("/api/stats")
def get_stats():
    """Статистика по проектам"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM projects")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM projects WHERE category = '@active'")
    active = cursor.fetchone()[0]
    
    cursor.execute("SELECT category, COUNT(*) FROM projects GROUP BY category")
    by_category = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    
    return {
        "total": total,
        "active": active,
        "by_category": by_category
    }

@app.post("/api/projects/{project_id}/launch")
def launch_project(project_id: int, editor: str = "windsurf"):
    """Запустить проект в редакторе (windsurf или antigravity)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT path FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")

    path = row[0]

    # Validate editor against configured editors
    cursor.execute(
        "SELECT command, args_template FROM editor_configs WHERE user_id = 'default' AND editor_id = ? AND is_enabled = 1",
        (editor,)
    )
    editor_row = cursor.fetchone()
    conn.close()

    if not editor_row:
        raise HTTPException(status_code=404, detail=f"Editor '{editor}' not found or not enabled")

    editor_command = editor_row[0]
    args_template = editor_row[1] or '{path}'

    # Build launch arguments from DB config
    args = args_template.replace('{path}', path).split()

    # Запуск в фоне
    try:
        subprocess.Popen([editor_command] + args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"Editor command '{editor_command}' not found on system")
    
    # Обновить статистику
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE projects 
        SET open_count = open_count + 1, last_opened = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (project_id,))
    conn.commit()
    conn.close()
    
    return {"status": "launched", "path": path, "editor": editor}

@app.get("/api/projects/{project_id}/docker")
def get_project_docker(project_id: int):
    """Получить Docker контейнеры проекта"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT path, name FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    
    path, name = row
    
    try:
        client = docker.from_env()
        containers = []
        
        for container in client.containers.list(all=True):
            # Check if container belongs to this project
            if name.lower() in container.name.lower() or path in str(container.labels):
                containers.append({
                    "id": container.id[:12],
                    "name": container.name,
                    "status": container.status,
                    "image": container.image.tags[0] if container.image.tags else "unknown",
                    "ports": container.ports
                })
        
        return {"containers": containers}
    except Exception as e:
        return {"containers": [], "error": str(e)}

@app.get("/api/projects/{project_id}/git")
def get_project_git(project_id: int):
    """Получить Git статус проекта"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT path FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    
    path = row[0]
    
    try:
        # Get current branch
        result = subprocess.run(
            ["git", "-C", path, "branch", "--show-current"],
            capture_output=True, text=True, timeout=5
        )
        branch = result.stdout.strip() if result.returncode == 0 else None
        
        # Get status
        result = subprocess.run(
            ["git", "-C", path, "status", "--porcelain"],
            capture_output=True, text=True, timeout=5
        )
        changes = len([l for l in result.stdout.strip().split('\n') if l]) if result.returncode == 0 else 0
        
        # Get last commit
        result = subprocess.run(
            ["git", "-C", path, "log", "-1", "--format=%h %s"],
            capture_output=True, text=True, timeout=5
        )
        last_commit = result.stdout.strip() if result.returncode == 0 else None
        
        return {
            "branch": branch,
            "changes": changes,
            "last_commit": last_commit,
            "is_git": branch is not None
        }
    except Exception as e:
        return {"is_git": False, "error": str(e)}

@app.get("/api/system")
def get_system_metrics():
    """Получить системные метрики (CPU/RAM/Disk/Uptime)"""
    import psutil
    
    # CPU
    cpu_percent = psutil.cpu_percent(interval=0.1)
    cpu_count = psutil.cpu_count()
    
    # RAM
    mem = psutil.virtual_memory()
    ram_used_mb = mem.used // (1024 * 1024)
    ram_total_mb = mem.total // (1024 * 1024)
    ram_percent = mem.percent
    
    # Disk
    disk = psutil.disk_usage('/')
    disk_used_gb = disk.used // (1024 * 1024 * 1024)
    disk_total_gb = disk.total // (1024 * 1024 * 1024)
    disk_percent = disk.percent
    
    # Uptime
    boot_time = psutil.boot_time()
    uptime_seconds = int(datetime.now().timestamp() - boot_time)
    uptime_days = uptime_seconds // 86400
    uptime_hours = (uptime_seconds % 86400) // 3600
    uptime_mins = (uptime_seconds % 3600) // 60
    
    return {
        "cpu": {
            "percent": cpu_percent,
            "cores": cpu_count,
            "status": "high" if cpu_percent > 80 else "medium" if cpu_percent > 50 else "normal"
        },
        "ram": {
            "used_mb": ram_used_mb,
            "total_mb": ram_total_mb,
            "percent": ram_percent,
            "status": "high" if ram_percent > 90 else "medium" if ram_percent > 75 else "normal"
        },
        "disk": {
            "used_gb": disk_used_gb,
            "total_gb": disk_total_gb,
            "percent": disk_percent,
            "status": "high" if disk_percent > 90 else "medium" if disk_percent > 75 else "normal"
        },
        "uptime": {
            "seconds": uptime_seconds,
            "days": uptime_days,
            "hours": uptime_hours,
            "minutes": uptime_mins,
            "formatted": f"{uptime_days}d {uptime_hours}h {uptime_mins}m" if uptime_days > 0 else f"{uptime_hours}h {uptime_mins}m"
        },
        "timestamp": datetime.now().isoformat()
    }

@app.put("/api/projects/{project_id}")
def update_project(project_id: int, project: Project):
    """Обновить проект (статус, теги, описание, лейбл)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE projects 
        SET status = ?, tags = ?, description = ?, label = ?
        WHERE id = ?
    ''', (project.status, json.dumps(project.tags), project.description, project.label, project_id))
    
    conn.commit()
    conn.close()
    
    return {"status": "updated"}

@app.post("/api/projects/{project_id}/label")
def set_project_label(project_id: int, label: str = Query(...)):
    """Установить лейбл проекта (favorite, working, archive или пусто)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Валидируем лейбл
    valid_labels = ["favorite", "working", "archive", ""]
    if label not in valid_labels:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Invalid label. Use: {valid_labels}")
    
    # Пустая строка = удалить лейбл
    label_value = label if label else None
    
    cursor.execute("UPDATE projects SET label = ? WHERE id = ?", (label_value, project_id))
    conn.commit()
    conn.close()
    
    return {"status": "updated", "label": label_value}

class ReorderRequest(BaseModel):
    project_ids: List[int]

@app.post("/api/projects/reorder")
def reorder_projects(request: ReorderRequest):
    """Изменить порядок проектов (custom sort)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Обновляем sort_order для каждого проекта
    for idx, project_id in enumerate(request.project_ids):
        cursor.execute("UPDATE projects SET sort_order = ? WHERE id = ?", (idx, project_id))
    
    conn.commit()
    conn.close()
    
    return {"status": "reordered", "count": len(request.project_ids)}

@app.post("/api/projects/{project_id}/move")
def move_project(project_id: int, direction: str = Query(...)):
    """Переместить проект вверх/вниз (up, down, top, bottom)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Получаем текущий порядок
    cursor.execute("SELECT id, sort_order FROM projects ORDER BY sort_order, name")
    projects = cursor.fetchall()
    
    # Находим индекс текущего проекта
    current_idx = None
    for idx, (pid, _) in enumerate(projects):
        if pid == project_id:
            current_idx = idx
            break
    
    if current_idx is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")
    
    new_idx = current_idx
    
    if direction == "up" and current_idx > 0:
        new_idx = current_idx - 1
    elif direction == "down" and current_idx < len(projects) - 1:
        new_idx = current_idx + 1
    elif direction == "top" and current_idx > 0:
        new_idx = 0
    elif direction == "bottom" and current_idx < len(projects) - 1:
        new_idx = len(projects) - 1
    else:
        conn.close()
        return {"status": "no_change", "message": f"Already at {'top' if direction == 'top' else 'bottom' if direction == 'bottom' else 'position'}"}
    
    # Меняем порядок
    if direction in ["up", "down"]:
        # Swap с соседом
        other_id, other_order = projects[new_idx]
        current_id, current_order = projects[current_idx]
        cursor.execute("UPDATE projects SET sort_order = ? WHERE id = ?", (other_order, current_id))
        cursor.execute("UPDATE projects SET sort_order = ? WHERE id = ?", (current_order, other_id))
    else:
        # Перемещаем в начало/конец - нужно пересчитать все
        project_ids = [p[0] for p in projects]
        if direction == "top":
            project_ids.remove(project_id)
            project_ids.insert(0, project_id)
        else:  # bottom
            project_ids.remove(project_id)
            project_ids.append(project_id)
        
        for idx, pid in enumerate(project_ids):
            cursor.execute("UPDATE projects SET sort_order = ? WHERE id = ?", (idx, pid))
    
    conn.commit()
    conn.close()
    
    return {"status": "moved", "direction": direction, "project_id": project_id}

@app.post("/api/projects/{project_id}/commands")
def add_command(project_id: int, cmd: Command):
    """Добавить команду запуска к проекту"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO commands (project_id, name, command, cwd) VALUES (?, ?, ?, ?)",
        (project_id, cmd.name, cmd.command, cmd.cwd)
    )
    
    cmd_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {"id": cmd_id, "status": "created"}

@app.get("/api/projects/{project_id}/commands")
def get_commands(project_id: int):
    """Получить команды проекта"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM commands WHERE project_id = ?", (project_id,))
    commands = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    return {"commands": commands}

@app.post("/api/projects/{project_id}/commands/{command_id}/run")
def run_command(project_id: int, command_id: int):
    """Запустить команду проекта"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT command, cwd FROM commands WHERE id = ?", (command_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Command not found")
    
    cmd, cwd = row

    # Run in terminal (escape values to prevent command injection)
    safe_cwd = shlex.quote(cwd or '.')
    safe_cmd = shlex.quote(cmd)
    subprocess.Popen(
        ["gnome-terminal", "--", "bash", "-c", f"cd {safe_cwd} && bash -c {safe_cmd}; exec bash"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    
    return {"status": "running", "command": cmd}

@app.post("/api/projects/{project_id}/open-folder")
def open_project_folder(project_id: int):
    """Открыть папку проекта в файловом менеджере"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT path FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    
    path = row[0]
    
    # Открываем в файловом менеджере (xdg-open для Linux)
    try:
        subprocess.Popen(
            ["xdg-open", path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return {"status": "opened", "path": path}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ==================== SETTINGS API ====================

@app.get("/api/settings")
def get_settings():
    """Получить все настройки пользователя"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT key, value, value_type, category FROM user_settings WHERE user_id = 'default'")
    settings = {row['key']: {'value': row['value'], 'type': row['value_type'], 'category': row['category']} for row in cursor.fetchall()}
    conn.close()
    
    return {"settings": settings}

@app.put("/api/settings")
def update_settings(settings: dict[str, SettingValue]):
    """Обновить настройки пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for key, data in settings.items():
        value = data.value
        value_type = data.type
        category = data.category
        
        cursor.execute('''
            INSERT INTO user_settings (user_id, key, value, value_type, category)
            VALUES ('default', ?, ?, ?, ?)
            ON CONFLICT(user_id, key) DO UPDATE SET
            value = excluded.value,
            value_type = excluded.value_type,
            category = excluded.category,
            updated_at = CURRENT_TIMESTAMP
        ''', (key, str(value), value_type, category))
    
    conn.commit()
    conn.close()
    
    return {"status": "updated"}

@app.get("/api/settings/editors")
def get_editors():
    """Получить список редакторов пользователя"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT editor_id, name, command, args_template, icon_path, color, 
               sort_order, is_enabled, is_default
        FROM editor_configs 
        WHERE user_id = 'default'
        ORDER BY sort_order ASC
    ''')
    editors = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {"editors": editors}

@app.post("/api/settings/editors")
def add_editor(editor: dict):
    """Добавить новый редактор"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    editor_id = editor.get('editor_id', editor['name'].lower().replace(' ', '_'))
    
    cursor.execute('''
        INSERT INTO editor_configs 
        (user_id, editor_id, name, command, args_template, icon_path, color, sort_order, is_enabled, is_default)
        VALUES ('default', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, editor_id) DO UPDATE SET
        name = excluded.name,
        command = excluded.command,
        args_template = excluded.args_template,
        icon_path = excluded.icon_path,
        color = excluded.color,
        is_enabled = excluded.is_enabled
    ''', (
        editor_id,
        editor.get('name'),
        editor.get('command'),
        editor.get('args_template', '{path}'),
        editor.get('icon_path'),
        editor.get('color', '#1f6feb'),
        editor.get('sort_order', 99),
        editor.get('is_enabled', True),
        editor.get('is_default', False)
    ))
    
    conn.commit()
    conn.close()
    
    return {"status": "created", "editor_id": editor_id}

@app.put("/api/settings/editors/{editor_id}")
def update_editor(editor_id: str, editor: dict):
    """Обновить редактор"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE editor_configs SET
        name = ?,
        command = ?,
        args_template = ?,
        icon_path = ?,
        color = ?,
        is_enabled = ?,
        is_default = ?
        WHERE user_id = 'default' AND editor_id = ?
    ''', (
        editor.get('name'),
        editor.get('command'),
        editor.get('args_template', '{path}'),
        editor.get('icon_path'),
        editor.get('color'),
        editor.get('is_enabled', True),
        editor.get('is_default', False),
        editor_id
    ))
    
    conn.commit()
    conn.close()
    
    return {"status": "updated"}

@app.delete("/api/settings/editors/{editor_id}")
def delete_editor(editor_id: str):
    """Удалить редактор"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM editor_configs WHERE user_id = 'default' AND editor_id = ?", (editor_id,))
    
    conn.commit()
    conn.close()
    
    return {"status": "deleted"}

@app.post("/api/settings/editors/reorder")
def reorder_editors(editor_ids: List[str]):
    """Изменить порядок редакторов"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for idx, editor_id in enumerate(editor_ids):
        cursor.execute('''
            UPDATE editor_configs SET sort_order = ? 
            WHERE user_id = 'default' AND editor_id = ?
        ''', (idx, editor_id))
    
    conn.commit()
    conn.close()
    
    return {"status": "reordered"}

@app.post("/api/settings/editors/{editor_id}/set-default")
def set_default_editor(editor_id: str):
    """Установить редактор по умолчанию"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Сбрасываем все is_default
    cursor.execute("UPDATE editor_configs SET is_default = 0 WHERE user_id = 'default'")
    
    # Устанавливаем новый default
    cursor.execute('''
        UPDATE editor_configs SET is_default = 1 
        WHERE user_id = 'default' AND editor_id = ?
    ''', (editor_id,))
    
    conn.commit()
    conn.close()
    
    return {"status": "updated", "default_editor": editor_id}

@app.post("/api/settings/editors/test")
def test_editor(editor: dict):
    """Тестовый запуск редактора"""
    command = editor.get('command')
    args = editor.get('args_template', '{path}').replace('{path}', '/tmp')
    full_cmd = f"{command} {args}"
    
    try:
        # Проверяем существование команды
        result = subprocess.run(
            ["which", command],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            return {"status": "error", "message": f"Command '{command}' not found in PATH"}
        
        return {"status": "ok", "command": full_cmd, "path": result.stdout.strip()}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/settings/i18n/{lang}")
def get_translations(lang: str):
    """Получить переводы для языка"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT key, value FROM translations WHERE lang_code = ?", (lang,))
    translations = {row['key']: row['value'] for row in cursor.fetchall()}
    conn.close()
    
    return {"lang": lang, "translations": translations}

@app.get("/api/settings/export")
def export_settings():
    """Экспорт всех настроек в JSON"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Получаем настройки
    cursor.execute("SELECT key, value, value_type, category FROM user_settings WHERE user_id = 'default'")
    settings = [dict(row) for row in cursor.fetchall()]
    
    # Получаем редакторы
    cursor.execute('''
        SELECT editor_id, name, command, args_template, icon_path, color, 
               sort_order, is_enabled, is_default
        FROM editor_configs WHERE user_id = 'default'
    ''')
    editors = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    export_data = {
        "version": "2.0",
        "exported_at": datetime.now().isoformat(),
        "settings": settings,
        "editors": editors
    }
    
    return export_data

@app.post("/api/settings/import")
def import_settings(data: dict):
    """Импорт настроек из JSON"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Импорт настроек
    for setting in data.get('settings', []):
        cursor.execute('''
            INSERT INTO user_settings (user_id, key, value, value_type, category)
            VALUES ('default', ?, ?, ?, ?)
            ON CONFLICT(user_id, key) DO UPDATE SET
            value = excluded.value,
            value_type = excluded.value_type,
            category = excluded.category,
            updated_at = CURRENT_TIMESTAMP
        ''', (setting['key'], setting['value'], setting['value_type'], setting['category']))
    
    # Импорт редакторов
    for editor in data.get('editors', []):
        cursor.execute('''
            INSERT INTO editor_configs 
            (user_id, editor_id, name, command, args_template, icon_path, color, sort_order, is_enabled, is_default)
            VALUES ('default', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, editor_id) DO UPDATE SET
            name = excluded.name,
            command = excluded.command,
            args_template = excluded.args_template,
            icon_path = excluded.icon_path,
            color = excluded.color,
            sort_order = excluded.sort_order,
            is_enabled = excluded.is_enabled,
            is_default = excluded.is_default
        ''', (
            editor['editor_id'], editor['name'], editor['command'],
            editor.get('args_template', '{path}'), editor.get('icon_path'),
            editor['color'], editor['sort_order'], editor['is_enabled'], editor['is_default']
        ))
    
    conn.commit()
    conn.close()
    
    return {"status": "imported", "settings_count": len(data.get('settings', [])), "editors_count": len(data.get('editors', []))}

@app.post("/api/settings/reset")
def reset_settings():
    """Сбросить настройки к дефолтным"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Удаляем пользовательские настройки
    cursor.execute("DELETE FROM user_settings WHERE user_id = 'default'")
    
    # Сбрасываем редакторы к дефолтным
    cursor.execute("DELETE FROM editor_configs WHERE user_id = 'default'")
    init_default_editors(cursor)
    
    conn.commit()
    conn.close()
    
    return {"status": "reset"}

# ==============================================================================
# ACTIVITY & LIVE API
# ==============================================================================

@app.get("/api/activity/heatmap")
def activity_heatmap():
    """Return daily open counts for last 84 days (12 weeks) for heatmap."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DATE(last_opened) as day, COUNT(*) as count
        FROM projects
        WHERE last_opened IS NOT NULL
          AND last_opened >= DATE('now', '-84 days')
        GROUP BY DATE(last_opened)
        ORDER BY day
    """)
    rows = cursor.fetchall()
    conn.close()
    data = {row[0]: row[1] for row in rows}

    # Fill all 84 days
    from datetime import date, timedelta
    result = []
    today = date.today()
    for i in range(83, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        result.append({"date": d, "count": data.get(d, 0)})
    return result


# ==============================================================================
# BRAIN API — Knowledge Base
# ==============================================================================

@app.get("/api/brain/stats")
def brain_stats():
    """Stats for Brain sidebar badge: total insights, projects with knowledge."""
    stats = {"total_projects": 0, "total_insights": 0, "last_updated": None}
    if not BRAIN_PROJECTS.exists():
        return stats
    files = list(BRAIN_PROJECTS.glob("*.md"))
    stats["total_projects"] = len(files)
    for f in files:
        content = f.read_text(errors="replace")
        stats["total_insights"] += len(re.findall(r"^### ", content, re.MULTILINE))
    if files:
        latest = max(files, key=lambda f: f.stat().st_mtime)
        stats["last_updated"] = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    return stats


@app.get("/api/brain/projects")
def brain_projects():
    """List all projects that have knowledge articles."""
    if not BRAIN_PROJECTS.exists():
        return []
    result = []
    for f in sorted(BRAIN_PROJECTS.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        content = f.read_text(errors="replace")
        insight_count = len(re.findall(r"^### ", content, re.MULTILINE))
        display = f.stem.replace("--", "/").replace("_", " ")
        mod_time = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        result.append({
            "slug": f.stem,
            "display_name": display,
            "insight_count": insight_count,
            "last_updated": mod_time,
        })
    return result


@app.get("/api/brain/projects/{slug}")
def brain_project_detail(slug: str):
    """Get full knowledge article for a project."""
    safe_slug = re.sub(r"[^a-zA-Z0-9@\-_]", "", slug)
    path = BRAIN_PROJECTS / f"{safe_slug}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Knowledge article not found")
    content = path.read_text(errors="replace")
    sections = []
    current = {"title": "Общее", "type": "other", "content": [], "tags": []}
    for line in content.splitlines():
        m = re.match(r"^### (.+?) — (.+)$", line)
        if m:
            if current["content"]:
                sections.append(current)
            current = {"title": m.group(1), "type": m.group(1).lower(), "date": m.group(2), "content": [], "tags": []}
        elif line.startswith("#"):
            pass
        elif re.match(r"^#\w", line):
            current["tags"] = re.findall(r"#(\w+)", line)
        else:
            current["content"].append(line)
    if current["content"]:
        sections.append(current)
    return {"slug": safe_slug, "sections": sections, "raw": content}


@app.post("/api/brain/log")
def brain_log(payload: dict):
    """Log a new insight from the dashboard UI."""
    project_name = payload.get("project_name", "").strip()
    insight_type = payload.get("insight_type", "other")
    content = payload.get("content", "").strip()
    tags = payload.get("tags", [])

    if not project_name or not content:
        raise HTTPException(status_code=400, detail="project_name and content are required")

    allowed_types = {"decision", "bug", "pattern", "gotcha", "stack", "qa", "other"}
    if insight_type not in allowed_types:
        insight_type = "other"

    BRAIN_DAILY.mkdir(parents=True, exist_ok=True)
    BRAIN_PROJECTS.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H:%M")
    daily_path = BRAIN_DAILY / f"{today}.md"
    tags_str = " ".join(f"#{t}" for t in tags) if tags else ""

    entry = (
        f"\n## [{timestamp}] {project_name}\n"
        f"**Type:** {insight_type}  \n"
        f"**Tags:** {tags_str}  \n\n"
        f"{content}\n\n---\n"
    )

    if not daily_path.exists():
        daily_path.write_text(f"# Daily Log — {today}\n\n*Записано через ProjectHub Brain*\n" + entry)
    else:
        with daily_path.open("a") as f:
            f.write(entry)

    safe_name = project_name.replace("/", "--").replace(" ", "_")
    proj_file = BRAIN_PROJECTS / f"{safe_name}.md"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_section = (
        f"\n## Обновление {now_str}\n\n"
        f"### {insight_type} — {now_str}\n"
        f"{tags_str}  \n\n{content}\n\n"
    )
    if proj_file.exists():
        with proj_file.open("a") as f:
            f.write(new_section)
    else:
        proj_file.write_text(
            f"# {project_name}\n\n"
            f"*Knowledge article. Создано: {now_str}*\n\n"
            f"## История решений\n"
            + new_section
        )

    return {"status": "ok", "daily_log": str(daily_path), "article": str(proj_file)}


@app.get("/api/brain/search")
def brain_search(q: str = Query(..., min_length=2)):
    """Full-text search across all knowledge articles."""
    if not BRAIN_PROJECTS.exists():
        return []
    results = []
    q_lower = q.lower()
    for f in BRAIN_PROJECTS.glob("*.md"):
        content = f.read_text(errors="replace")
        if q_lower in content.lower():
            lines = [l for l in content.splitlines() if q_lower in l.lower()]
            display = f.stem.replace("--", "/").replace("_", " ")
            results.append({
                "slug": f.stem,
                "display_name": display,
                "matches": lines[:5],
            })
    return results


@app.get("/api/brain/project-insights/{project_name:path}")
def project_insight_count(project_name: str):
    """Get insight count for a specific project (for dashboard cards)."""
    safe_name = project_name.replace("/", "--").replace(" ", "_")
    path = BRAIN_PROJECTS / f"{safe_name}.md"
    if not path.exists():
        return {"count": 0, "last_updated": None}
    content = path.read_text(errors="replace")
    count = len(re.findall(r"^### ", content, re.MULTILINE))
    mod_time = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
    return {"count": count, "last_updated": mod_time}


# ── MCP Connect API ──────────────────────────────────────────────────────────

MCP_SERVER_PATH = Path(__file__).parent.parent / "mcp-server" / "server.py"
MCP_VENV_PYTHON = Path(__file__).parent.parent / "mcp-server" / ".venv" / "bin" / "python"

IDE_DEFINITIONS = [
    {
        "id": "windsurf",
        "name": "Windsurf",
        "description": "Codeium Windsurf / Cascade",
        "icon": "wind",
        "color": "#1DB9C3",
        "config_paths": [
            Path.home() / ".config" / "Qoder" / "User" / "mcp.json",
            Path.home() / ".codeium" / "windsurf" / "mcp_config.json",
        ],
        "config_key": "mcpServers",
        "server_name": "project-context",
    },
    {
        "id": "cursor",
        "name": "Cursor",
        "description": "Cursor AI Editor",
        "icon": "mouse-pointer-2",
        "color": "#146EF5",
        "config_paths": [
            Path.home() / ".cursor" / "mcp.json",
            Path.home() / ".config" / "Cursor" / "User" / "mcp.json",
        ],
        "config_key": "mcpServers",
        "server_name": "project-context",
    },
    {
        "id": "claude",
        "name": "Claude Code",
        "description": "Anthropic Claude Code CLI",
        "icon": "terminal",
        "color": "#D97757",
        "config_paths": [
            Path.home() / ".claude" / "mcp_servers.json",
            Path.home() / "Library" / "Application Support" / "Claude" / "mcp_servers.json",
        ],
        "config_key": "mcpServers",
        "server_name": "project-context",
    },
    {
        "id": "vscode",
        "name": "VS Code",
        "description": "Visual Studio Code + Copilot",
        "icon": "code-2",
        "color": "#007ACC",
        "config_paths": [
            Path.home() / ".vscode" / "mcp.json",
            Path.home() / ".config" / "Code" / "User" / "mcp.json",
        ],
        "config_key": "servers",
        "server_name": "project-context",
    },
    {
        "id": "zed",
        "name": "Zed",
        "description": "Zed Editor with AI Assistant",
        "icon": "zap",
        "color": "#084CCF",
        "config_paths": [
            Path.home() / ".config" / "zed" / "settings.json",
        ],
        "config_key": "context_servers",
        "server_name": "project-context",
    },
    {
        "id": "neovim",
        "name": "Neovim",
        "description": "Neovim + mcphub.nvim plugin",
        "icon": "terminal-square",
        "color": "#57A143",
        "config_paths": [
            Path.home() / ".config" / "nvim" / "mcp.json",
        ],
        "config_key": "mcpServers",
        "server_name": "project-context",
    },
    {
        "id": "jetbrains",
        "name": "JetBrains",
        "description": "IntelliJ IDEA / PyCharm / WebStorm",
        "icon": "boxes",
        "color": "#FE315D",
        "config_paths": [
            Path.home() / ".config" / "JetBrains" / "mcp.json",
            Path.home() / ".jetbrains" / "mcp.json",
        ],
        "config_key": "mcpServers",
        "server_name": "project-context",
    },
    {
        "id": "continue",
        "name": "Continue",
        "description": "Continue.dev — open-source AI assistant",
        "icon": "play-circle",
        "color": "#6C4FF6",
        "config_paths": [
            Path.home() / ".continue" / "config.json",
        ],
        "config_key": "mcpServers",
        "server_name": "project-context",
    },
    {
        "id": "aider",
        "name": "Aider",
        "description": "Aider AI pair programmer (CLI)",
        "icon": "git-merge",
        "color": "#E44D26",
        "config_paths": [
            Path.home() / ".aider" / "mcp.json",
        ],
        "config_key": "mcpServers",
        "server_name": "project-context",
    },
    {
        "id": "antigravity",
        "name": "AntiGravity",
        "description": "AntiGravity AI Code Editor",
        "icon": "rocket",
        "color": "#8B5CF6",
        "config_paths": [
            Path.home() / ".config" / "AntiGravity" / "User" / "mcp.json",
            Path.home() / ".antigravity" / "mcp.json",
        ],
        "config_key": "mcpServers",
        "server_name": "project-context",
    },
    {
        "id": "void",
        "name": "Void",
        "description": "Void — open-source Cursor alternative",
        "icon": "circle-dot",
        "color": "#3B3B3B",
        "config_paths": [
            Path.home() / ".void" / "mcp.json",
            Path.home() / ".config" / "Void" / "User" / "mcp.json",
        ],
        "config_key": "mcpServers",
        "server_name": "project-context",
    },
    {
        "id": "trae",
        "name": "Trae",
        "description": "Trae AI IDE by ByteDance",
        "icon": "cpu",
        "color": "#1677FF",
        "config_paths": [
            Path.home() / ".trae" / "mcp.json",
            Path.home() / ".config" / "Trae" / "User" / "mcp.json",
        ],
        "config_key": "mcpServers",
        "server_name": "project-context",
    },
    {
        "id": "gemini-cli",
        "name": "Gemini CLI",
        "description": "Google Gemini CLI",
        "icon": "sparkles",
        "color": "#4285F4",
        "config_paths": [
            Path.home() / ".gemini" / "mcp.json",
            Path.home() / ".config" / "gemini-cli" / "mcp.json",
        ],
        "config_key": "mcpServers",
        "server_name": "project-context",
    },
]

def _get_mcp_entry() -> dict:
    python_bin = str(MCP_VENV_PYTHON) if MCP_VENV_PYTHON.exists() else "python3"
    return {
        "command": python_bin,
        "args": [str(MCP_SERVER_PATH)]
    }

@app.get("/api/mcp/detect")
def detect_ides():
    """Detect installed IDEs and MCP connection status"""
    results = []
    for ide in IDE_DEFINITIONS:
        found_path = None
        connected = False
        for p in ide["config_paths"]:
            if p.exists():
                found_path = str(p)
                try:
                    cfg = json.loads(p.read_text())
                    servers = cfg.get(ide["config_key"], {})
                    connected = ide["server_name"] in servers
                except Exception:
                    pass
                break

        results.append({
            "id": ide["id"],
            "name": ide["name"],
            "description": ide["description"],
            "icon": ide["icon"],
            "color": ide["color"],
            "installed": found_path is not None,
            "connected": connected,
            "config_path": found_path,
        })
    return {"ides": results, "mcp_server_exists": MCP_SERVER_PATH.exists()}

@app.post("/api/mcp/connect/{ide_id}")
def connect_ide(ide_id: str):
    """Inject MCP config into IDE config file"""
    ide = next((i for i in IDE_DEFINITIONS if i["id"] == ide_id), None)
    if not ide:
        raise HTTPException(status_code=404, detail="Unknown IDE")

    if not MCP_SERVER_PATH.exists():
        raise HTTPException(status_code=400, detail=f"MCP server not found at {MCP_SERVER_PATH}")

    # Find existing config or use first path
    config_path = None
    for p in ide["config_paths"]:
        if p.exists():
            config_path = p
            break
    if not config_path:
        config_path = ide["config_paths"][0]
        config_path.parent.mkdir(parents=True, exist_ok=True)

    # Load or create config
    try:
        cfg = json.loads(config_path.read_text()) if config_path.exists() else {}
    except Exception:
        cfg = {}

    if ide["config_key"] not in cfg:
        cfg[ide["config_key"]] = {}

    cfg[ide["config_key"]][ide["server_name"]] = _get_mcp_entry()

    config_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    return {
        "success": True,
        "ide": ide["name"],
        "config_path": str(config_path),
        "message": f"Restart {ide['name']} to activate MCP tools"
    }

@app.delete("/api/mcp/connect/{ide_id}")
def disconnect_ide(ide_id: str):
    """Remove MCP config from IDE config file"""
    ide = next((i for i in IDE_DEFINITIONS if i["id"] == ide_id), None)
    if not ide:
        raise HTTPException(status_code=404, detail="Unknown IDE")

    for p in ide["config_paths"]:
        if p.exists():
            try:
                cfg = json.loads(p.read_text())
                if ide["config_key"] in cfg and ide["server_name"] in cfg[ide["config_key"]]:
                    del cfg[ide["config_key"]][ide["server_name"]]
                    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
                    return {"success": True, "ide": ide["name"], "config_path": str(p)}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    return {"success": False, "message": "Config not found"}


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")

# Монтируем static директорию для иконок и других ресурсов
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8472)
