from decimal import Decimal
from pydantic import BaseModel as PydanticBaseModel, ConfigDict, field_validator, model_validator


class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator('*', mode='after')
    @classmethod
    def validate_values(cls, value, info):
        if isinstance(value, Decimal):
            if not value.is_finite() or abs(value) > Decimal('9999999999.99') or value != value.quantize(Decimal('.01')):
                raise ValueError('Valor deve ter no máximo 10 dígitos inteiros e 2 casas decimais')
        if isinstance(value, str) and info.field_name not in ('password', 'current_password', 'new_password'):
            lengths = {'name': 100, 'full_name': 100, 'responsible_name': 100, 'alias_name': 100,
                       'bank_name': 100, 'agency': 20, 'account_number': 30, 'color': 20,
                       'icon': 50, 'brand': 50, 'last_digits': 4}
            maximum = lengths.get(info.field_name, 10000)
            if info.field_name == 'name' and cls.__name__.startswith('FinancialGoal'):
                maximum = 150
            if info.field_name == 'description' and cls.__name__.startswith(('Transaction', 'Installment')):
                maximum = 255
            if len(value) > maximum:
                raise ValueError('Texto excede o limite de 10000 caracteres')
        return value

    @model_validator(mode='after')
    def reject_null_required_updates(self):
        if type(self).__name__.endswith('Update'):
            nullable = {'category_id', 'destination_account_id', 'card_id', 'payment_method_id',
                        'notes', 'description', 'bank_name', 'agency', 'account_number',
                        'last_digits', 'responsible_id', 'target_date'}
            if type(self).__name__ == 'CreditCardUpdate':
                nullable |= {'account_id', 'responsible_name'}
            if type(self).__name__ == 'TransactionUpdate':
                nullable.discard('description')
            for name in self.model_fields_set:
                if getattr(self, name) is None and name not in nullable:
                    raise ValueError(f'{name} não pode ser nulo')
        return self
