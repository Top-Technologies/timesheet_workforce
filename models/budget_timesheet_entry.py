from odoo import api, fields, models
from datetime import timedelta


class BudgetTimesheetEntry(models.Model):
    """Worker card – one record per worker. Daily work lines go underneath."""
    _name = 'budget.timesheet.entry'
    _description = 'Workforce Timesheet Entry'
    _order = 'name desc'
    _inherit = ['mail.thread']

    # ── Reference ───────────────────────────────────────────────
    name = fields.Char(
        string="Reference",
        default='New',
        readonly=True,
        copy=False,
        tracking=True,
    )

    # ── State ───────────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
    ], string="Status", default='draft', tracking=True, copy=False)

    # ── Worker Information ──────────────────────────────────────
    partner_id = fields.Many2one(
        'res.partner',
        string="Worker",
        required=True,
        tracking=True,
        help="Select the worker from Contacts.",
    )
    worker_name = fields.Char(
        related='partner_id.name',
        string="Worker Name",
        store=True,
        readonly=True,
    )

    # ── Bank / Payment Details (hidden, auto-filled from contact) ──
    account_number = fields.Char(
        string="Account Number",
        help="Auto-filled from the contact's first bank account.",
    )
    account_holder_name = fields.Char(
        string="Account Holder Name",
    )

    # ── Category & Budget Link ──────────────────────────────────
    category_id = fields.Many2one(
        'budget.timesheet.category',
        string="Worker Category",
        required=True,
        tracking=True,
        help="Determines the default unit price for work lines.",
    )
    budget_plan_line_id = fields.Many2one(
        'budget.plan.line',
        string="Budget Plan Item",
        tracking=True,
        help="Link to the budgeted item to track consumption.",
    )
    budget_plan_id = fields.Many2one(
        'budget.plan',
        string="Budget Plan",
        related='budget_plan_line_id.budget_plan_id',
        store=True,
        readonly=True,
    )
    department_id = fields.Many2one(
        'hr.department',
        string="Department",
        related='budget_plan_line_id.department_id',
        store=True,
        readonly=True,
    )

    # ── Work Lines ──────────────────────────────────────────────
    line_ids = fields.One2many(
        'budget.timesheet.entry.line',
        'entry_id',
        string="Work Lines",
    )

    # ── Totals ──────────────────────────────────────────────────
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
    line_count = fields.Integer(
        string="Work Days",
        compute='_compute_totals',
        store=True,
    )

    # ── Standard Fields ─────────────────────────────────────────
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
    notes = fields.Text(string="Notes")

    # ── Sequence ────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'budget.timesheet.entry') or 'New'
        return super().create(vals_list)

    # ── Workflow Actions ────────────────────────────────────────
    def action_submit(self):
        """User submits the card for manager approval."""
        for rec in self:
            rec.state = 'submitted'

    def action_approve(self):
        """Manager approves the card and auto-updates weekly summaries."""
        for rec in self:
            rec.state = 'approved'
        # Auto-generate/refresh weekly summaries for affected weeks
        self.env['budget.timesheet.weekly.summary'].action_generate_summaries()

    def action_refuse(self):
        """Manager refuses – sends back to draft for corrections."""
        for rec in self:
            rec.state = 'draft'

    def action_reset_draft(self):
        """Reset to draft state."""
        for rec in self:
            rec.state = 'draft'

    # ── Onchanges ───────────────────────────────────────────────
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """Auto-fill bank details from the contact's first bank account."""
        if self.partner_id:
            bank = self.env['res.partner.bank'].search(
                [('partner_id', '=', self.partner_id.id)], limit=1)
            if bank:
                self.account_number = bank.acc_number
                self.account_holder_name = bank.acc_holder_name or self.partner_id.name
            else:
                self.account_number = False
                self.account_holder_name = self.partner_id.name

    # ── Computed Fields ─────────────────────────────────────────
    @api.depends('line_ids.amount', 'line_ids.unit_hours')
    def _compute_totals(self):
        for rec in self:
            rec.total_hours = sum(rec.line_ids.mapped('unit_hours'))
            rec.total_amount = sum(rec.line_ids.mapped('amount'))
            rec.line_count = len(rec.line_ids)

    def action_view_work_lines(self):
        """Open standalone list of work lines for this worker card."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Work Lines - {self.worker_name}',
            'res_model': 'budget.timesheet.entry.line',
            'view_mode': 'list',
            'domain': [('entry_id', '=', self.id)],
            'context': {'default_entry_id': self.id},
        }

    def action_open_print_wizard(self):
        """Open date range wizard before printing payslip."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Print Payslip',
            'res_model': 'workforce.print.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_entry_id': self.id},
        }


class BudgetTimesheetEntryLine(models.Model):
    """Individual work day line under a worker card."""
    _name = 'budget.timesheet.entry.line'
    _description = 'Workforce Timesheet Work Line'
    _order = 'date desc, id desc'

    entry_id = fields.Many2one(
        'budget.timesheet.entry',
        string="Timesheet Entry",
        required=True,
        ondelete='cascade',
    )

    # ── Related fields from parent (for list/search convenience) ──
    worker_name = fields.Char(
        related='entry_id.worker_name',
        string="Worker",
        store=True,
        readonly=True,
    )
    category_id = fields.Many2one(
        related='entry_id.category_id',
        string="Category",
        store=True,
        readonly=True,
    )
    budget_plan_line_id = fields.Many2one(
        related='entry_id.budget_plan_line_id',
        string="Budget Plan Item",
        store=True,
        readonly=True,
    )
    department_id = fields.Many2one(
        related='entry_id.department_id',
        string="Department",
        store=True,
        readonly=True,
    )
    account_number = fields.Char(
        related='entry_id.account_number',
        string="Account Number",
        store=True,
        readonly=True,
    )
    account_holder_name = fields.Char(
        related='entry_id.account_holder_name',
        string="Account Holder",
        store=True,
        readonly=True,
    )

    # ── Line-specific fields ────────────────────────────────────
    date = fields.Date(
        string="Work Date",
        required=True,
        default=fields.Date.context_today,
    )
    unit = fields.Selection(
        [('full_day', 'Full Day (8 hrs)'),
         ('half_day', 'Half Day (4 hrs)')],
        string="Unit",
        required=True,
        default='full_day',
    )
    unit_hours = fields.Float(
        string="Hours",
        compute='_compute_unit_hours',
        store=True,
    )
    unit_price = fields.Monetary(
        string="Unit Price",
        currency_field='currency_id',
        help="Auto-filled from worker category. Editable per line.",
    )
    amount = fields.Monetary(
        string="Amount",
        currency_field='currency_id',
        compute='_compute_amount',
        store=True,
        help="Unit Hours × Unit Price",
    )
    currency_id = fields.Many2one(
        related='entry_id.currency_id',
        store=True,
    )
    notes = fields.Char(string="Notes")

    # ── Auto-increment date ───────────────────────────────────────
    @api.model
    def default_get(self, fields_list):
        """Auto-set date to the day after the last existing line."""
        res = super().default_get(fields_list)
        if 'date' in fields_list:
            entry_id = self.env.context.get('default_entry_id')
            if entry_id:
                last_line = self.search(
                    [('entry_id', '=', entry_id)],
                    order='date desc, id desc',
                    limit=1,
                )
                if last_line and last_line.date:
                    res['date'] = last_line.date + timedelta(days=1)
        return res

    # ── Onchanges ───────────────────────────────────────────────
    @api.onchange('unit')
    def _onchange_unit(self):
        """Auto-fill unit_price from parent category when adding a new line."""
        if self.entry_id and self.entry_id.category_id and not self.unit_price:
            self.unit_price = self.entry_id.category_id.unit_price

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-fill unit_price from parent category on create if not set."""
        for vals in vals_list:
            if not vals.get('unit_price') and vals.get('entry_id'):
                entry = self.env['budget.timesheet.entry'].browse(vals['entry_id'])
                if entry.category_id:
                    vals['unit_price'] = entry.category_id.unit_price
        return super().create(vals_list)

    # ── Computed Fields ─────────────────────────────────────────
    @api.depends('unit')
    def _compute_unit_hours(self):
        for rec in self:
            rec.unit_hours = 8.0 if rec.unit == 'full_day' else 4.0

    @api.depends('unit_hours', 'unit_price')
    def _compute_amount(self):
        for rec in self:
            rec.amount = rec.unit_hours * (rec.unit_price or 0.0)
