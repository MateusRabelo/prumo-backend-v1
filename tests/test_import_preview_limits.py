import pytest
from pydantic import ValidationError
from app.schemas.statement_import import ImportConfirm


def test_signed_preview_has_its_own_limit_without_loosening_transaction_names():
    body={'preview_token':'x'*35000,'reviewed':True,'entries':[{'index':0,'description':'Compra','type':'DESPESA'}]}
    assert len(ImportConfirm.model_validate(body).preview_token)==35000
    with pytest.raises(ValidationError):ImportConfirm.model_validate({**body,'preview_token':'x'*800001})
    with pytest.raises(ValidationError):ImportConfirm.model_validate({**body,'entries':[{'index':0,'description':'x'*256,'type':'DESPESA'}]})
