# TODO: move to a separate repository or at least python-mip
from sklearn.linear_model import SGDRegressor, SGDClassifier
import titus.prettypfa


def sklearn_to_pfa(estimator, types):
    """
    Convert scikit-learn estimator to PFA format.
    :param estimator: Scikit-learn estimator, must be supported
    :param types: List of tuples (name, type)
    """
    types = _fix_types_compatibility(types)

    if isinstance(estimator, SGDRegressor):
        return _pfa_sgdregressor(estimator, types)
    elif isinstance(estimator, SGDClassifier):
        return _pfa_sgdclassifier(estimator, types)
    else:
        raise NotImplementedError('Estimator {} is not yet supported'.format(estimator.__class__.__name__))


def _pfa_sgdregressor(estimator, types):
    """
    Example output:
        input: record(Data,
            feature0: double,
            feature1: double,
        )
        output: double
        action:
            -2.525797382870301 + 31.7004451488 * input.feature0 + 42.5005713274 * input.feature1
    """
    formula = _regression_formula(estimator, types)
    input_record = _input_record(types)

    pretty_pfa = """
input: {input_record}
output: double
action:
    {formula}
    """.format(
        input_record=input_record, formula=formula
    ).strip()

    pfa = titus.prettypfa.jsonNode(pretty_pfa)

    return pfa


def _pfa_sgdclassifier(estimator, types):
    """
    Example output:
        types:
            Query = record(Query,
                           sql: string,
                           variable: string,
                           covariables: array(string));
            Input = record(Input,
                a: double,
                b: double
            );
            Regression = record(Regression, const: double, coeff: array(double));
        input: Input
        output: string
        cells:
            query(Query) = {sql: SELECT, variable: dep, covariables: [a, b, c]};
            model(array(Regression)) = [
                {const: 3, coeff: [1, 2]},
                {const: 3, coeff: [1, 4]}
            ];
            classes(array(string)) = [a, b, c];
        fcns:
            featurize = fcn(x: Input -> array(double))
                new(array(double),
                    x.a,
                    x.b
                )
        action:
            // TODO: define this as a function when functions start working with titus python 3
            var x = new(array(double),
                input.a,
                input.b
            );
            var scores = a.map(model, fcn(r: Regression -> double) model.reg.linear(x, r));
            classes[a.argmax(scores)]
    """
    input_record = _input_record(types)
    featurizer = _construct_featurizer(types)

    # construct template
    pretty_pfa = """
types:
    Query = record(Query,
                   sql: string,
                   variable: string,
                   covariables: array(string));
    Regression = record(Regression, const: double, coeff: array(double));
    Input = {input_record}
input: Input
output: string
cells:
    // query(Query) = {{}};
    model(array(Regression)) = [];
    classes(array(string)) = [];
action:
    var x = {featurizer};
    var scores = a.map(model, fcn(r: Regression -> double) model.reg.linear(x, r));
    classes[a.argmax(scores)]
    """.format(
        input_record=input_record, featurizer=featurizer
    ).strip()

    # compile
    pfa = titus.prettypfa.jsonNode(pretty_pfa)

    # add model from scikit-learn
    pfa['cells']['classes']['init'] = list(estimator.classes_)
    pfa['cells']['model']['init'] = [{'const': const, 'coeff': list(coeff)} for const, coeff in zip(estimator.intercept_, estimator.coef_)]

    return pfa


def _construct_featurizer(types):
    inputs = ',\n'.join(['input.' + name for name, _ in types])
    return """
new(array(double),
    {inputs}
    );
    """.format(inputs=inputs)


def _regression_formula(estimator, types):
    """
    Create regression formula from estimator's coefficients.

    Example output:
        1.2 + 3.45 * input.featureA + 6.78 * input.featureB
    """
    feature_names = ['input.' + c for c, _ in types]
    return ' + '.join(
        [str(estimator.intercept_[0])] + ['{} * {}'.format(a, b) for a, b in zip(estimator.coef_, feature_names)]
    )


def _input_record(types):
    s = 'record(Input'
    for name, typ in types:
        s += ',\n    {}: {}'.format(name, typ)
    return s + '\n);'


def _fix_types_compatibility(types):
    new_types = []
    for name, typ in types:
        if typ == 'real':
            typ = 'double'
        new_types.append((name, typ))
    return new_types