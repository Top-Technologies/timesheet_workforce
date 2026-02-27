{
    'name': 'Workforce Timesheet',
    'version': '18.0.1.3.1',
    'summary': 'Track workforce time and payments linked to Budget Plan',
    'description': '''
        Track daily work hours for employees and contractors,
        calculate payments, and link consumption back
        to the Budget Plan module.
    ''',
    'category': 'Services/Timesheets',
    'author': 'Top Tech',
    'license': 'LGPL-3',
    'depends': ['hr_timesheet', 'budget_plan', 'hr'],
    'data': [
        'security/budget_timesheet_groups.xml',
        'security/ir.model.access.csv',
        'wizard/workforce_print_wizard_views.xml',
        'report/report_workforce_entry.xml',
        'views/budget_timesheet_category_views.xml',
        'views/budget_timesheet_entry_views.xml',
        'views/budget_timesheet_weekly_summary_views.xml',
        'views/budget_timesheet_menus.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
