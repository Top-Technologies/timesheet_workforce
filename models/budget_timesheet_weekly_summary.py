from odoo import api, fields, models, _
from odoo.exceptions import UserError
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
    purchase_order_ids = fields.One2many(
        'purchase.order',
        'weekly_summary_id',
        string="RFQs / Purchase Orders",
    )
    purchase_order_count = fields.Integer(
        string="RFQs Count",
        compute='_compute_rfq_info',
    )
    has_pending_rfq = fields.Boolean(
        string="Has Pending RFQ",
        compute='_compute_rfq_info',
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
    @api.depends('line_ids.entry_id.partner_id', 'purchase_order_ids.state', 'purchase_order_ids.partner_id')
    def _compute_rfq_info(self):
        for rec in self:
            rec.purchase_order_count = len(rec.purchase_order_ids)
            active_pos = rec.purchase_order_ids.filtered(lambda p: p.state != 'cancel')
            active_partners = active_pos.mapped('partner_id')
            summary_partners = rec.line_ids.mapped('entry_id.partner_id')
            rec.has_pending_rfq = bool(
                summary_partners and any(p not in active_partners for p in summary_partners)
            )

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

    # ── Status Actions & Purchase Order Creation ────────────────
    def action_view_purchase_orders(self):
        """Open the purchase orders linked to this weekly summary."""
        self.ensure_one()
        pos = self.purchase_order_ids
        action = {
            'type': 'ir.actions.act_window',
            'name': f'Purchase Orders - {self.name}',
            'res_model': 'purchase.order',
            'context': {'default_weekly_summary_id': self.id},
        }
        if len(pos) == 1:
            action['view_mode'] = 'form'
            action['res_id'] = pos.id
        else:
            action['view_mode'] = 'list,form'
            action['domain'] = [('id', 'in', pos.ids)]
        return action

    @api.model
    def _get_or_create_workforce_product(self, category=None):
        """Retrieve or create a default service product for workforce timesheets."""
        Product = self.env['product.product']
        name = f"Workforce - {category.name}" if category else "Workforce Labor"

        # 1. Search existing by exact name
        product = Product.search([('name', '=', name)], limit=1)
        if product:
            return product

        # 2. Search any existing service product with workforce or timesheet
        product = Product.search([
            ('type', '=', 'service'),
            ('name', 'ilike', 'workforce')
        ], limit=1)
        if product:
            return product

        # 3. Create a service product
        return Product.create({
            'name': name,
            'type': 'service',
            'purchase_ok': True,
            'sale_ok': False,
        })

    def _create_purchase_orders(self):
        """Create purchase orders for each worker in the weekly summary.
        Populates every related detail: starting week/dates, touched budget plan
        and item, worker name, product item, money amounts, and category."""
        PurchaseOrder = self.env['purchase.order']
        created_pos = PurchaseOrder

        for rec in self:
            if not rec.line_ids:
                continue

            # Identify partners that already have an active (non-cancelled) RFQ/PO
            active_pos = rec.purchase_order_ids.filtered(lambda po: po.state != 'cancel')
            existing_partners = active_pos.mapped('partner_id')

            # Group lines by worker (partner_id)
            workers = {}
            for line in rec.line_ids:
                partner = line.entry_id.partner_id
                if not partner:
                    continue
                # Skip partner if they already have an active RFQ/PO for this summary
                if partner in existing_partners:
                    continue
                if partner not in workers:
                    workers[partner] = []
                workers[partner].append(line)

            for partner, lines in workers.items():
                bp_lines = self.env['budget.plan.line']
                po_lines_vals = []

                for line in lines:
                    entry = line.entry_id
                    bp_line = entry.budget_plan_line_id
                    bp = bp_line.budget_plan_id if bp_line else (line.budget_plan_id or False)
                    category = line.category_id

                    if bp_line:
                        bp_lines |= bp_line

                    # Determine product
                    product = False
                    if bp_line and bp_line.product_id:
                        product = bp_line.product_id
                    elif category and hasattr(category, 'product_id') and category.product_id:
                        product = category.product_id
                    else:
                        product = self._get_or_create_workforce_product(category)

                    # Determine UoM
                    uom = (bp_line.uom_id if bp_line and bp_line.uom_id
                           else (product.uom_po_id or product.uom_id))

                    # Calculate quantity and unit price to preserve exact total amount
                    qty = line.total_hours if line.total_hours > 0 else 1.0
                    unit_price = (line.total_amount / qty) if qty else (line.unit_price or 0.0)

                    # Format descriptive line name
                    currency_symbol = rec.currency_id.symbol or ''
                    line_desc = (
                        f"Workforce Timesheet: {line.worker_name or partner.name}\n"
                        f"• Worker: {line.worker_name or partner.name}\n"
                        f"• Category: {category.name if category else 'General'}\n"
                        f"• Period / Start: {rec.date_from} to {rec.date_to} (Week #{rec.week_number}, {rec.year})\n"
                        f"• Budget Plan: {bp.name if bp else 'N/A'}\n"
                        f"• Budget Item: {bp_line.name if bp_line else 'N/A'} ({product.display_name})\n"
                        f"• Total Hours: {line.total_hours:.2f} hrs @ {currency_symbol}{unit_price:.2f} / hr\n"
                        f"• Total Amount: {currency_symbol}{line.total_amount:.2f}"
                    )

                    po_line_vals = {
                        'product_id': product.id,
                        'name': line_desc,
                        'product_qty': qty,
                        'product_uom': uom.id if uom else False,
                        'price_unit': unit_price,
                        'date_planned': rec.date_to or fields.Date.today(),
                        'budget_plan_id': bp.id if bp else False,
                        'budget_plan_line_id': bp_line.id if bp_line else False,
                        'worker_partner_id': partner.id,
                        'worker_category_id': category.id if category else False,
                        'weekly_summary_id': rec.id,
                        'weekly_summary_line_id': line.id,
                    }
                    if bp_line and bp_line.analytic_distribution:
                        po_line_vals['analytic_distribution'] = bp_line.analytic_distribution

                    po_lines_vals.append((0, 0, po_line_vals))

                if not po_lines_vals:
                    continue

                # Default picking type (incoming destination)
                picking_type_id = False
                for bpl in bp_lines:
                    if bpl.picking_type_id:
                        picking_type_id = bpl.picking_type_id.id
                        break
                if not picking_type_id:
                    picking_type = self.env['stock.picking.type'].search([
                        ('code', '=', 'incoming'),
                        ('company_id', '=', rec.company_id.id),
                    ], limit=1)
                    if picking_type:
                        picking_type_id = picking_type.id

                # Notes for PO
                bp_plans = bp_lines.mapped('budget_plan_id')
                if not bp_plans:
                    bp_plans = lines.mapped('budget_plan_id')
                bp_names = ', '.join(bp_plans.mapped('name')) or 'N/A'
                po_notes = (
                    f"Workforce Timesheet Payment Summary\n"
                    f"Summary: {rec.name}\n"
                    f"Period: {rec.date_from} to {rec.date_to} (Week #{rec.week_number}, {rec.year})\n"
                    f"Worker: {partner.name}\n"
                    f"Budget Plan(s) Touched: {bp_names}"
                )

                po_vals = {
                    'partner_id': partner.id,
                    'company_id': rec.company_id.id,
                    'currency_id': rec.currency_id.id,
                    'date_order': fields.Datetime.now(),
                    'origin': f"Workforce: {rec.name}",
                    'notes': po_notes,
                    'weekly_summary_id': rec.id,
                    'budget_plan_id': bp_plans[0].id if bp_plans else False,
                    'budget_plan_ids': [(6, 0, bp_plans.ids)],
                    'budget_plan_line_ids': [(6, 0, bp_lines.ids)],
                    'order_line': po_lines_vals,
                }
                if picking_type_id:
                    po_vals['picking_type_id'] = picking_type_id

                po = PurchaseOrder.create(po_vals)
                created_pos |= po

                # Chatter message on weekly summary
                rec.message_post(
                    body=(
                        f"RFQ <b><a href='#id={po.id}&amp;model=purchase.order'>{po.name}</a></b> "
                        f"created for worker <b>{partner.name}</b> (Amount: {rec.currency_id.symbol or ''}{sum(l.total_amount for l in lines):.2f})."
                    ),
                    message_type='comment',
                    subtype_xmlid='mail.mt_note',
                )

                # Chatter message on PO
                po.message_post(
                    body=(
                        f"Generated from Workforce Weekly Summary "
                        f"<b><a href='#id={rec.id}&amp;model=budget.timesheet.weekly.summary'>{rec.name}</a></b>."
                    ),
                    message_type='comment',
                    subtype_xmlid='mail.mt_note',
                )

        return created_pos

    def action_mark_paid(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Cannot mark as paid: this weekly summary has no worker lines."))
            rec.state = 'paid'

    def action_create_rfq(self):
        """Create RFQ (Purchase Order in draft) for workers in the weekly summary."""
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Cannot create RFQ: '%s' has no worker lines.") % rec.name)
            if not rec.has_pending_rfq:
                raise UserError(_("All RFQs have already been created for '%s'.") % rec.name)

        created_pos = self._create_purchase_orders()
        if not created_pos:
            raise UserError(_("No RFQ could be created. Please verify that worker partner records are set on the timesheet entries."))

        if len(created_pos) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('RFQ - %s') % created_pos.name,
                'res_model': 'purchase.order',
                'res_id': created_pos.id,
                'view_mode': 'form',
                'target': 'current',
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'name': _('RFQs - %s') % self.name,
                'res_model': 'purchase.order',
                'domain': [('id', 'in', created_pos.ids)],
                'view_mode': 'list,form',
                'target': 'current',
            }

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
