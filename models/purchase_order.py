from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    weekly_summary_id = fields.Many2one(
        'budget.timesheet.weekly.summary',
        string="Weekly Timesheet Summary",
        copy=False,
        index=True,
        help="Weekly workforce timesheet summary from which this purchase order was generated.",
    )
    budget_plan_id = fields.Many2one(
        'budget.plan',
        string="Budget Plan",
        compute='_compute_budget_plans',
        store=True,
        readonly=False,
        copy=False,
        help="Budget Plan linked to this RFQ / Purchase Order.",
    )
    budget_plan_ids = fields.Many2many(
        'budget.plan',
        'purchase_order_budget_plan_rel',
        'order_id',
        'budget_plan_id',
        string="Budget Plans",
        compute='_compute_budget_plans',
        store=True,
        readonly=False,
        copy=False,
        help="All Budget Plans linked to this RFQ / Purchase Order.",
    )
    budget_plan_count = fields.Integer(
        string="Budget Plans Count",
        compute='_compute_budget_plans',
        store=True,
    )

    @api.depends('budget_plan_line_ids.budget_plan_id',
                 'order_line.budget_plan_id',
                 'order_line.budget_plan_line_id.budget_plan_id')
    def _compute_budget_plans(self):
        for po in self:
            plans = (
                po.budget_plan_line_ids.mapped('budget_plan_id') |
                po.order_line.mapped('budget_plan_id') |
                po.order_line.mapped('budget_plan_line_id.budget_plan_id')
            )
            po.budget_plan_ids = [(6, 0, plans.ids)]
            po.budget_plan_count = len(plans)
            if plans and not po.budget_plan_id:
                po.budget_plan_id = plans[0]
            elif not plans:
                po.budget_plan_id = False


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    worker_partner_id = fields.Many2one(
        'res.partner',
        string="Worker",
        copy=False,
        help="Worker associated with this timesheet expense.",
    )
    worker_category_id = fields.Many2one(
        'budget.timesheet.category',
        string="Worker Category",
        copy=False,
        help="Workforce category (e.g. IT Config, Carpenter).",
    )
    weekly_summary_id = fields.Many2one(
        'budget.timesheet.weekly.summary',
        string="Weekly Summary",
        copy=False,
        index=True,
    )
    weekly_summary_line_id = fields.Many2one(
        'budget.timesheet.weekly.summary.line',
        string="Weekly Summary Line",
        copy=False,
    )
    budget_plan_id = fields.Many2one(
        'budget.plan',
        string="Budget Plan",
        compute='_compute_budget_plan_id',
        store=True,
        readonly=False,
        copy=False,
        help="Budget Plan associated with this Purchase Order line.",
    )

    @api.depends('budget_plan_line_id.budget_plan_id')
    def _compute_budget_plan_id(self):
        for line in self:
            if line.budget_plan_line_id and line.budget_plan_line_id.budget_plan_id:
                line.budget_plan_id = line.budget_plan_line_id.budget_plan_id
            elif not line.budget_plan_id:
                line.budget_plan_id = False

    @api.onchange('budget_plan_id')
    def _onchange_budget_plan_id(self):
        if self.budget_plan_id and self.budget_plan_line_id:
            if self.budget_plan_line_id.budget_plan_id != self.budget_plan_id:
                self.budget_plan_line_id = False
