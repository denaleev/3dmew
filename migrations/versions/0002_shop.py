"""shop: published products, orders with history, custom print requests with files, shop settings, admin flag

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('shop_settings',
    sa.Column('key', sa.String(length=40), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('custom_requests',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('token', sa.String(length=40), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('phone', sa.String(length=60), nullable=False),
    sa.Column('email', sa.String(length=160), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('size', sa.String(length=160), nullable=False),
    sa.Column('color', sa.String(length=160), nullable=False),
    sa.Column('qty', sa.Integer(), nullable=False),
    sa.Column('budget', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('quote_price', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('quote_cost', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('quote_minutes', sa.Integer(), nullable=True),
    sa.Column('quote_grams', sa.Numeric(precision=10, scale=1), nullable=True),
    sa.Column('quote_text', sa.Text(), nullable=False),
    sa.Column('admin_note', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_custom_requests_created_at'), 'custom_requests', ['created_at'], unique=False)
    op.create_index(op.f('ix_custom_requests_status'), 'custom_requests', ['status'], unique=False)
    op.create_index(op.f('ix_custom_requests_token'), 'custom_requests', ['token'], unique=False)
    op.create_index(op.f('ix_custom_requests_user_id'), 'custom_requests', ['user_id'], unique=False)
    op.create_table('orders',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('token', sa.String(length=40), nullable=False),
    sa.Column('user_id', sa.String(length=32), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('phone', sa.String(length=60), nullable=False),
    sa.Column('email', sa.String(length=160), nullable=False),
    sa.Column('delivery', sa.String(length=40), nullable=False),
    sa.Column('address', sa.Text(), nullable=False),
    sa.Column('comment', sa.Text(), nullable=False),
    sa.Column('admin_note', sa.Text(), nullable=False),
    sa.Column('total', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('cost', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('print_minutes', sa.Integer(), nullable=False),
    sa.Column('grams', sa.Numeric(precision=10, scale=1), nullable=False),
    sa.Column('paid', sa.Boolean(), nullable=False),
    sa.Column('request_id', sa.Integer(), nullable=True),
    sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['request_id'], ['custom_requests.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_orders_created_at'), 'orders', ['created_at'], unique=False)
    op.create_index(op.f('ix_orders_status'), 'orders', ['status'], unique=False)
    op.create_index(op.f('ix_orders_token'), 'orders', ['token'], unique=False)
    op.create_index(op.f('ix_orders_user_id'), 'orders', ['user_id'], unique=False)
    op.create_table('products',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('item_id', sa.String(length=40), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('features', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=80), nullable=False),
    sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('old_price', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('cost', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('calc', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('print_minutes', sa.Integer(), nullable=False),
    sa.Column('grams', sa.Numeric(precision=10, scale=1), nullable=False),
    sa.Column('material', sa.String(length=60), nullable=False),
    sa.Column('stock', sa.Integer(), nullable=False),
    sa.Column('published', sa.Boolean(), nullable=False),
    sa.Column('sort', sa.Integer(), nullable=False),
    sa.Column('image', sa.LargeBinary(), nullable=True),
    sa.Column('thumb', sa.LargeBinary(), nullable=True),
    sa.Column('views', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['items.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('item_id')
    )
    op.create_table('request_files',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('request_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('mime', sa.String(length=120), nullable=False),
    sa.Column('size', sa.BigInteger(), nullable=False),
    sa.Column('data', sa.LargeBinary(), nullable=False),
    sa.Column('thumb', sa.LargeBinary(), nullable=True),
    sa.ForeignKeyConstraint(['request_id'], ['custom_requests.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_request_files_request_id'), 'request_files', ['request_id'], unique=False)
    op.create_table('order_events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.Column('request_id', sa.Integer(), nullable=True),
    sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('who', sa.String(length=160), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('text', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['request_id'], ['custom_requests.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_order_events_order_id'), 'order_events', ['order_id'], unique=False)
    op.create_index(op.f('ix_order_events_request_id'), 'order_events', ['request_id'], unique=False)
    op.create_table('order_items',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('cost', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('qty', sa.Integer(), nullable=False),
    sa.Column('print_minutes', sa.Integer(), nullable=False),
    sa.Column('grams', sa.Numeric(precision=10, scale=1), nullable=False),
    sa.Column('note', sa.String(length=300), nullable=False),
    sa.Column('from_stock', sa.Integer(), server_default='0', nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_order_items_order_id'), 'order_items', ['order_id'], unique=False)
    op.create_index(op.f('ix_order_items_product_id'), 'order_items', ['product_id'], unique=False)
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'is_admin')
    op.drop_index(op.f('ix_order_items_product_id'), table_name='order_items')
    op.drop_index(op.f('ix_order_items_order_id'), table_name='order_items')
    op.drop_table('order_items')
    op.drop_index(op.f('ix_order_events_request_id'), table_name='order_events')
    op.drop_index(op.f('ix_order_events_order_id'), table_name='order_events')
    op.drop_table('order_events')
    op.drop_index(op.f('ix_request_files_request_id'), table_name='request_files')
    op.drop_table('request_files')
    op.drop_table('products')
    op.drop_index(op.f('ix_orders_user_id'), table_name='orders')
    op.drop_index(op.f('ix_orders_token'), table_name='orders')
    op.drop_index(op.f('ix_orders_status'), table_name='orders')
    op.drop_index(op.f('ix_orders_created_at'), table_name='orders')
    op.drop_table('orders')
    op.drop_index(op.f('ix_custom_requests_user_id'), table_name='custom_requests')
    op.drop_index(op.f('ix_custom_requests_token'), table_name='custom_requests')
    op.drop_index(op.f('ix_custom_requests_status'), table_name='custom_requests')
    op.drop_index(op.f('ix_custom_requests_created_at'), table_name='custom_requests')
    op.drop_table('custom_requests')
    op.drop_table('shop_settings')
