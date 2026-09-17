"""add_agent_platform_tables

Revision ID: c1a2b3c4d5e6
Revises: b2ae330a2811
Create Date: 2026-06-21

Creates all tables for the Agent platform (SQLAlchemy 2.0 models).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c1a2b3c4d5e6'
down_revision = 'b2ae330a2811'
branch_labels = None
depends_on = None


def upgrade():
    # ── Provider configs ──
    op.create_table(
        'provider_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('provider_type', sa.String(50), nullable=False),
        sa.Column('api_key', sa.Text(), nullable=False),
        sa.Column('base_url', sa.String(500), nullable=True),
        sa.Column('model_name', sa.String(100), nullable=False),
        sa.Column('config', postgresql.JSON, server_default='{}', nullable=False),
        sa.Column('is_active', sa.Boolean, server_default='true', nullable=False),
        sa.Column('is_default', sa.Boolean, server_default='false', nullable=False),
        sa.Column('fallback_order', sa.Integer, server_default='999', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_provider_configs_user_id', 'provider_configs', ['user_id'])

    # ── Conversations ──
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', sa.String(255), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(255), server_default='新对话', nullable=False),
        sa.Column('persona_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_conversations_session_id', 'conversations', ['session_id'])
    op.create_index('ix_conversations_user_id', 'conversations', ['user_id'])

    # ── Messages ──
    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', postgresql.JSON, nullable=False),
        sa.Column('tool_calls', postgresql.JSON, nullable=True),
        sa.Column('tool_call_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])

    # ── Knowledge bases ──
    op.create_table(
        'knowledge_bases',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('embedding_provider_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('chunk_size', sa.Integer, server_default='500', nullable=False),
        sa.Column('chunk_overlap', sa.Integer, server_default='50', nullable=False),
        sa.Column('retrieval_mode', sa.String(20), server_default='inject', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_knowledge_bases_user_id', 'knowledge_bases', ['user_id'])

    # ── Documents ──
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('kb_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('knowledge_bases.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename', sa.String(500), nullable=False),
        sa.Column('file_path', sa.String(1000), nullable=False),
        sa.Column('status', sa.String(20), server_default='pending', nullable=False),
        sa.Column('chunks_count', sa.Integer, server_default='0', nullable=False),
        sa.Column('file_size', sa.Integer, server_default='0', nullable=False),
        sa.Column('file_type', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_documents_kb_id', 'documents', ['kb_id'])
    op.create_index('ix_documents_user_id', 'documents', ['user_id'])

    # ── MCP servers ──
    op.create_table(
        'mcp_servers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('transport_type', sa.String(20), nullable=False),
        sa.Column('url', sa.String(1000), nullable=True),
        sa.Column('command', sa.String(500), nullable=True),
        sa.Column('args', postgresql.JSON, server_default='[]', nullable=False),
        sa.Column('env_vars', postgresql.JSON, server_default='{}', nullable=False),
        sa.Column('is_active', sa.Boolean, server_default='true', nullable=False),
        sa.Column('tools', postgresql.JSON, server_default='[]', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_mcp_servers_user_id', 'mcp_servers', ['user_id'])

    # ── Skills ──
    op.create_table(
        'skills',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('path', sa.String(1000), nullable=False),
        sa.Column('source_type', sa.String(20), server_default='local', nullable=False),
        sa.Column('is_active', sa.Boolean, server_default='true', nullable=False),
        sa.Column('config', postgresql.JSON, server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # ── Personas ──
    op.create_table(
        'personas',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('avatar', sa.String(500), nullable=True),
        sa.Column('default_provider_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('tools', postgresql.JSON, server_default='[]', nullable=False),
        sa.Column('is_active', sa.Boolean, server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_personas_user_id', 'personas', ['user_id'])

    # ── Agent runs (tracking) ──
    op.create_table(
        'agent_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('persona_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('input_text', sa.Text(), nullable=False),
        sa.Column('output_text', sa.Text(), nullable=True),
        sa.Column('tool_calls_made', sa.Integer, server_default='0', nullable=False),
        sa.Column('tokens_used', sa.Integer, server_default='0', nullable=False),
        sa.Column('duration_ms', sa.Integer, nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_agent_runs_conversation_id', 'agent_runs', ['conversation_id'])
    op.create_index('ix_agent_runs_user_id', 'agent_runs', ['user_id'])


def downgrade():
    op.drop_table('agent_runs')
    op.drop_table('personas')
    op.drop_table('skills')
    op.drop_table('mcp_servers')
    op.drop_table('documents')
    op.drop_table('knowledge_bases')
    op.drop_table('messages')
    op.drop_table('conversations')
    op.drop_table('provider_configs')
