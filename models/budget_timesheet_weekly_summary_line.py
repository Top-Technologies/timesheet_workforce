from odoo import api, fields, models


class BudgetTimesheetWeeklySummaryLine(models.Model):
    """One row per worker in a weekly summary."""
    _name = 'budget.timesheet.weekly.summary.line'
    _description = 'Weekly Summary Worker Line'
    _order = 'worker_name'

    summary_id = fields.Many2one(
        'budget.timesheet.weekly.summary',
        string="Weekly Summary",
        required=True,
        ondelete='cascade',
    )
    entry_id = fields.Many2one(
        'budget.timesheet.entry',
        string="Worker Card",
        required=True,
    )

    # Related fields from worker card (for display)
    worker_name = fields.Char(
        related='entry_id.worker_name',
        string="Worker",
        store=True,
        readonly=True,
    )
    account_number = fields.Char(
        related='entry_id.account_number',
        string="Account Number",
        store=True,
        readonly=True,
    )
    category_id = fields.Many2one(
        related='entry_id.category_id',
        string="Category",
        store=True,
        readonly=True,
    )
    unit_price = fields.Monetary(
        related='entry_id.category_id.unit_price',
        string="Unit Price",
        store=True,
        readonly=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        related='summary_id.currency_id',
        store=True,
    )

    partner_id = fields.Many2one(
        related='entry_id.partner_id',
        string="Worker Contact",
        store=True,
        readonly=True,
    )
    budget_plan_line_id = fields.Many2one(
        related='entry_id.budget_plan_line_id',
        string="Budget Plan Item",
        store=True,
        readonly=True,
    )
    budget_plan_id = fields.Many2one(
        related='entry_id.budget_plan_id',
        string="Budget Plan",
        store=True,
        readonly=True,
    )

    # Aggregated values (set by the refresh action)
    total_hours = fields.Float(string="Total Hours")
    total_amount = fields.Monetary(
        string="Total Amount",
        currency_field='currency_id',
    )
    purchase_order_line_ids = fields.One2many(
        'purchase.order.line',
        'weekly_summary_line_id',
        string="Purchase Order Lines",
    )
