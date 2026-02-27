from odoo import api, fields, models
from datetime import timedelta


class BudgetTimesheetWeeklySummary(models.Model):
    """One record per week — aggregates all approved workers for that period."""
    _name = 'budget.timesheet.weekly.summary'
    _description = 'Weekly Payment Summary'
    _order = 'date_from desc'
    _inherit = ['mail.thread']

    name = fields.Char(
        string="Week",
        compute='_compute_name',
        store=True,
    )
    date_from = fields.Date(
        string="Week Start",
        required=True,
        tracking=True,
    )
    date_to = fields.Date(
        string="Week End",
        required=True,
        tracking=True,
    )
    week_number = fields.Integer(
        string="Week #",
        compute='_compute_week_info',
        store=True,
    )
    year = fields.Integer(
        string="Year",
        compute='_compute_week_info',
        store=True,
    )
    state = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('on_the_way', 'On the Way'),
        ('paid', 'Paid'),
    ], string="Payment Status", default='unpaid', tracking=True)

    line_ids = fields.One2many(
        'budget.timesheet.weekly.summary.line',
        'summary_id',
        string="Worker Lines",
    )
    worker_count = fields.Integer(
        string="Workers",
        compute='_compute_totals',
        store=True,
    )
    total_hours = fields.Float(
        string="Total Hours",
        compute='_compute_totals',
        store=True,
    )
    total_amount = fields.Monetary(
        string="Total Amount",
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        default=lambda self: self.env.company.currency_id.id,
        required=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        default=lambda self: self.env.company,
        readonly=True,
    )

    _sql_constraints = [
        ('date_range_uniq', 'unique(date_from, date_to, company_id)',
         'A weekly summary already exists for this date range.'),
    ]

    # ── Computed Fields ─────────────────────────────────────────
    @api.depends('date_from', 'date_to')
    def _compute_name(self):
        for rec in self:
            if rec.date_from and rec.date_to:
                week_num = rec.date_from.isocalendar()[1]
                rec.name = "Week %02d (%s – %s)" % (
                    week_num,
                    rec.date_from.strftime('%b %d'),
                    rec.date_to.strftime('%b %d, %Y'),
                )
            else:
                rec.name = "New"

    @api.depends('date_from')
    def _compute_week_info(self):
        for rec in self:
            if rec.date_from:
                iso = rec.date_from.isocalendar()
                rec.week_number = iso[1]
                rec.year = iso[0]
            else:
                rec.week_number = 0
                rec.year = 0

    @api.depends('line_ids.total_hours', 'line_ids.total_amount')
    def _compute_totals(self):
        for rec in self:
            rec.worker_count = len(rec.line_ids)
            rec.total_hours = sum(rec.line_ids.mapped('total_hours'))
            rec.total_amount = sum(rec.line_ids.mapped('total_amount'))

    # ── Status Actions ──────────────────────────────────────────
    def action_mark_paid(self):
        for rec in self:
            rec.state = 'paid'

    def action_mark_on_the_way(self):
        for rec in self:
            rec.state = 'on_the_way'

    def action_mark_unpaid(self):
        for rec in self:
            rec.state = 'unpaid'

    # ── Generate / Refresh Lines ────────────────────────────────
    def action_refresh_lines(self):
        """Scan approved worker entries and (re)build summary lines
        for the date range of this weekly summary."""
        for rec in self:
            # Find all approved entries that have work lines in the date range
            work_lines = self.env['budget.timesheet.entry.line'].search([
                ('date', '>=', rec.date_from),
                ('date', '<=', rec.date_to),
                ('entry_id.state', '=', 'approved'),
            ])

            # Group by entry (worker card)
            entries_data = {}
            for wl in work_lines:
                entry = wl.entry_id
                if entry.id not in entries_data:
                    entries_data[entry.id] = {
                        'entry_id': entry.id,
                        'total_hours': 0.0,
                        'total_amount': 0.0,
                    }
                entries_data[entry.id]['total_hours'] += wl.unit_hours
                entries_data[entry.id]['total_amount'] += wl.amount

            # Clear old lines and create fresh ones
            rec.line_ids.unlink()
            for entry_id, data in entries_data.items():
                self.env['budget.timesheet.weekly.summary.line'].create({
                    'summary_id': rec.id,
                    'entry_id': entry_id,
                    'total_hours': data['total_hours'],
                    'total_amount': data['total_amount'],
                })

    # ── Print consolidated PDF ──────────────────────────────────
    def action_print_summary(self):
        """Print the consolidated weekly summary PDF."""
        self.ensure_one()
        return self.env.ref(
            'timesheet_workforce.action_report_weekly_summary'
        ).report_action(self, data={
            'summary_id': self.id,
            'date_from': str(self.date_from),
            'date_to': str(self.date_to),
        })

    # ── Bulk Generate Summaries ─────────────────────────────────
    @api.model
    def action_generate_summaries(self):
        """Generate weekly summary records for all weeks that have
        approved work lines but no summary yet."""
        # Find date range of all approved work lines
        lines = self.env['budget.timesheet.entry.line'].search([
            ('entry_id.state', '=', 'approved'),
        ], order='date asc')

        if not lines:
            return

        # Get the min and max dates
        min_date = lines[0].date
        max_date = lines[-1].date

        # Iterate week by week
        # Start from Monday of min_date's week
        start = min_date - timedelta(days=min_date.weekday())

        while start <= max_date:
            end = start + timedelta(days=6)  # Sunday

            # Check if any approved work lines exist for this week
            week_lines = lines.filtered(
                lambda l: start <= l.date <= end
            )

            existing = self.search([
                ('date_from', '=', start),
                ('date_to', '=', end),
            ], limit=1)

            if week_lines:
                if not existing:
                    summary = self.create({
                        'date_from': start,
                        'date_to': end,
                    })
                    summary.action_refresh_lines()
                else:
                    existing.action_refresh_lines()
            elif existing and not existing.line_ids:
                # Remove empty summaries (no workers)
                existing.unlink()

            start += timedelta(days=7)
