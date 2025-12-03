"""added enum fields

Revision ID: b146e3eba4f4
Revises: f48ea40d4a8b
Create Date: 2025-12-03 12:40:25.742203

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b146e3eba4f4'
down_revision: Union[str, Sequence[str], None] = 'f48ea40d4a8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create ENUM types first - INCLUDING pending_activation
    message_role_enum = postgresql.ENUM('user', 'assistant', 'system', name='message_role_enum', create_type=False)
    message_role_enum.create(op.get_bind(), checkfirst=True)
    
    user_status_enum = postgresql.ENUM('active', 'inactive', 'suspended', 'deleted', 'pending_activation', name='user_status_enum', create_type=False)
    user_status_enum.create(op.get_bind(), checkfirst=True)
    
    # Now alter columns to use the ENUM types
    op.alter_column('messages', 'role',
               existing_type=sa.VARCHAR(length=20),
               type_=message_role_enum,
               existing_nullable=False,
               postgresql_using='role::text::message_role_enum')
    
    op.drop_constraint(op.f('fk_org_owner'), 'organizations', type_='foreignkey')
    op.create_foreign_key('fk_org_owner', 'organizations', 'users', ['owner_user_id'], ['user_id'], ondelete='RESTRICT', initially='DEFERRED', deferrable=True)
    
    op.alter_column('users', 'status',
               existing_type=sa.VARCHAR(length=20),
               type_=user_status_enum,
               nullable=False,
               postgresql_using='status::text::user_status_enum')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('users', 'status',
               existing_type=postgresql.ENUM('active', 'inactive', 'suspended', 'deleted', 'pending_activation', name='user_status_enum'),
               type_=sa.VARCHAR(length=20),
               nullable=True)
    
    op.drop_constraint('fk_org_owner', 'organizations', type_='foreignkey')
    op.create_foreign_key(op.f('fk_org_owner'), 'organizations', 'users', ['owner_user_id'], ['user_id'], ondelete='RESTRICT')
    
    op.alter_column('messages', 'role',
               existing_type=postgresql.ENUM('user', 'assistant', 'system', name='message_role_enum'),
               type_=sa.VARCHAR(length=20),
               existing_nullable=False)
    
    # Drop ENUM types after reverting columns
    postgresql.ENUM(name='user_status_enum').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='message_role_enum').drop(op.get_bind(), checkfirst=True)