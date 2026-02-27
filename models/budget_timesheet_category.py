from odoo import api, fields, models


class BudgetTimesheetCategory(models.Model):
    _name = 'budget.timesheet.category'
    _description = 'Worker Category'
    _order = 'name'

    name = fields.Char(
        string="Category Name",
        required=True,
        help="e.g. Carpenter, Plumber, Electrician",
    )
    code = fields.Char(
        string="Code",
        help="Short code, e.g. CARP, PLMB",
    )
    unit_price = fields.Monetary(
        string="Unit Price",
        currency_field='currency_id',
        required=True,
        help="Rate per unit (full-day or half-day price base). "
             "This value is multiplied by unit hours on each entry.",
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        default=lambda self: self.env.company.currency_id.id,
        required=True,
    )
    active = fields.Boolean(string="Active", default=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Category name must be unique.'),
    ]
