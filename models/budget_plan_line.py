from odoo import api, fields, models


class BudgetPlanLine(models.Model):
    _inherit = 'budget.plan.line'

    timesheet_entry_ids = fields.One2many(
        'budget.timesheet.entry',
        'budget_plan_line_id',
        string="Workforce Entries",
    )
    timesheet_entry_count = fields.Integer(
        string="Entries Count",
        compute='_compute_timesheet_entry_count',
    )
    timesheet_consumed_qty = fields.Float(
        string="Workforce Consumed",
        compute='_compute_timesheet_consumed_qty',
        store=True,
        help="Total worker-day units consumed from linked workforce entries.",
    )
    timesheet_consumed_amount = fields.Monetary(
        string="Workforce Cost",
        currency_field='currency_id',
        compute='_compute_timesheet_consumed_qty',
        store=True,
        help="Total monetary cost from linked workforce entries.",
    )

    def _compute_timesheet_entry_count(self):
        for rec in self:
            rec.timesheet_entry_count = len(rec.timesheet_entry_ids)

    @api.depends(
        'timesheet_entry_ids.line_ids',
        'timesheet_entry_ids.line_ids.unit',
        'timesheet_entry_ids.line_ids.amount',
    )
    def _compute_timesheet_consumed_qty(self):
        for rec in self:
            total_days = 0.0
            total_amount = 0.0
            for entry in rec.timesheet_entry_ids:
                for line in entry.line_ids:
                    total_days += 1.0 if line.unit == 'full_day' else 0.5
                    total_amount += line.amount
            rec.timesheet_consumed_qty = total_days
            rec.timesheet_consumed_amount = total_amount

    def action_view_timesheet_entries(self):
        """Open a list of workforce entries linked to this budget plan line."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Workforce Entries',
            'res_model': 'budget.timesheet.entry',
            'view_mode': 'list,form',
            'domain': [('budget_plan_line_id', '=', self.id)],
            'context': {'default_budget_plan_line_id': self.id},
        }
