from odoo import api, fields, models


class WorkforcePrintWizard(models.TransientModel):
    """Wizard to select date range before printing the payslip PDF."""
    _name = 'workforce.print.wizard'
    _description = 'Workforce Payslip Print Wizard'

    entry_id = fields.Many2one(
        'budget.timesheet.entry',
        string="Worker Card",
        required=True,
    )
    date_from = fields.Date(
        string="From",
        required=True,
    )
    date_to = fields.Date(
        string="To",
        required=True,
        default=fields.Date.context_today,
    )

    # Preview of filtered lines
    preview_line_ids = fields.Many2many(
        'budget.timesheet.entry.line',
        string="Work Lines Preview",
        compute='_compute_preview_lines',
    )
    preview_total = fields.Float(
        string="Total Amount",
        compute='_compute_preview_lines',
    )
    preview_count = fields.Integer(
        string="Lines Count",
        compute='_compute_preview_lines',
    )

    @api.onchange('date_to')
    def _onchange_date_to(self):
        """Default date_from to first day of the same month as date_to."""
        if self.date_to and not self.date_from:
            self.date_from = self.date_to.replace(day=1)

    @api.depends('entry_id', 'date_from', 'date_to')
    def _compute_preview_lines(self):
        for rec in self:
            if rec.entry_id and rec.date_from and rec.date_to:
                lines = rec.entry_id.line_ids.filtered(
                    lambda l: rec.date_from <= l.date <= rec.date_to
                )
                rec.preview_line_ids = lines
                rec.preview_total = sum(lines.mapped('amount'))
                rec.preview_count = len(lines)
            else:
                rec.preview_line_ids = False
                rec.preview_total = 0
                rec.preview_count = 0

    def action_print(self):
        """Generate the payslip PDF with work lines filtered by date range."""
        self.ensure_one()
        lines = self.entry_id.line_ids.filtered(
            lambda l: self.date_from <= l.date <= self.date_to
        )
        data = {
            'entry_id': self.entry_id.id,
            'date_from': str(self.date_from),
            'date_to': str(self.date_to),
            'line_ids': lines.ids,
        }
        return self.env.ref(
            'timesheet_workforce.action_report_workforce_payslip'
        ).report_action(self.entry_id, data=data)
