
from django.dispatch import Signal
from types import MethodType

from inspect import getargspec

__doc__ = """
    example:

    >>> class Spaceship(object):
    ...     def __init__(spaceship):
    ...         spaceship.lives = 3
    ...
    ...     has_collided = SignalMethod(('spaceship', 'asteroid'))
    ...
    ...     def explode(spaceship):
    ...         print 'Boom!'
    ...
    ...     def lose_life(spaceship):
    ...         spaceship.lives -= 1
    ...         if spaceship.lives == 0:
    ...             print 'Game Over'

    >>> class Asteroid(object):
    ...     def destroy(asteroid):
    ...         assert isinstance(asteroid, Asteroid)
    ...         print 'asteroid destroyed'

    >>> asteroid = Asteroid()
    >>> spaceship = Spaceship()

    Now:

        Spaceship.has_collided.send(sender=Spaceship, spaceship=spaceship, asteroid=asteroid)

    can be written as:

        spaceship.has_collided(asteroid=asteroid)

    >>> rule = when(Spaceship.has_collided)(Spaceship.explode)

    >>> responses = spaceship.has_collided(asteroid=asteroid)
    Boom!

    >>> rule.stop()

    Multiple effects can be provided:

    >>> rule = when(Spaceship.has_collided)(
    ...     Spaceship.explode,
    ...     spaceship.lose_life, # calling bound methods is OK
    ...     Asteroid.destroy
    ... )

    >>> responses = spaceship.has_collided(asteroid=asteroid)
    Boom!
    asteroid destroyed

    >>> rule.stop()

    More complex rules can be handled as a decorated function:
    note that defaults can be supplied and these then are optional arguments.
    
    >>> @when(Spaceship.has_collided)
    ... def destroy_spaceship_and_asteroid(spaceship, asteroid=asteroid):
    ...     asteroid.destroy()
    ...     if not hasattr(spaceship, 'forcefield'):
    ...         spaceship.explode()
    ...         spaceship.lose_life()

    >>> responses = spaceship.has_collided()
    asteroid destroyed
    Boom!

    >>> destroy_spaceship_and_asteroid.stop()

    Note that non-kwyword arguments will be mapped to the correct name,
    and that unneeded arguments are just ignored, and that no arguments
    are required (as they may have defaults, like make_noise.
    also **kwargs can be given, like django signal handlers mandate.

    >>> @when(Spaceship.has_collided)
    ... def destroy_spaceship_and_asteroid(spaceship, asteroid, make_noise=True, **kwargs):
    ...     asteroid.destroy()
    ...     spaceship.explode()
    ...     spaceship.lose_life()

    >>> responses = spaceship.has_collided(Asteroid(), aliens=False)
    asteroid destroyed
    Boom!
    Game Over

    Also note that if needed arguments are missing, the usual errors come through:

    >>> responses = spaceship.has_collided()
    Traceback (most recent call last):
    TypeError: destroy_spaceship_and_asteroid() takes at least 2 arguments (1 given)

"""


class SignalMethod(Signal):
    """Allows signals to be used as instance methods.

    'sender' argument will be the class where the signal method is accessed.
    The first provided argument of the signal will be the same as 'self'.
    """

    def __init__(signal_method, providing_args=None, name=None):
        super(SignalMethod, signal_method).__init__(providing_args)
        signal_method.name = name
        signal_method.providing_args = providing_args

    def __get__(signal_method, obj, type=None):
        def unbound_send(self_arg, *args, **kwargs):
            # turn args into kwargs, according to providing_args order
            kwargs[signal_method.providing_args[0]] = self_arg
            for index, arg in enumerate(args):
                kwargs[signal_method.providing_args[index+1]] = arg
            return signal_method.send(
                sender=type,
                _kwargs=kwargs
            )
        unbound_send.signal = signal_method
        return MethodType(
            unbound_send,
            obj,
            type,
        )


class SignalHandlingRule(object):
    """SignalHandlingRule that applies signal handling.

    SignalHandlingRules can be used as context managers and decorators
    """
    def __init__(rule, unbound_signal_method, receivers, id=None):
        rule.SendingClass = unbound_signal_method.im_class
        rule.signal = unbound_signal_method.im_func.signal
        rule.id = id
        rule.receivers = receivers
        rule.arg_rules = dict()
        provided_args = rule.signal.providing_args
        for receiver in receivers:
            arg_spec = getargspec(receiver)
            arg_keys = arg_spec.args
            if isinstance(receiver, MethodType):
                if receiver.im_self is None:
                    needed_self_arg_name = arg_keys[0]
                    if needed_self_arg_name not in provided_args:
                        raise TypeError(
                            "%(receiver)s requires argument '%(needed_self_arg_name)s' but signal doesn't send it.\n"
                            "Consider renaming '%(needed_self_arg_name)s' to one of %(provided_args)s \n"
                            "or decorating a function that calls %(receiver)s on one of the passed arguments"
                            "%(provided_args)s." % locals()
                        )
                else:
                    # first (self) arg has already been supplied, so can be ignored
                    arg_keys.pop(0)
            var_args = arg_spec.varargs
            if var_args:
                raise TypeError(
                    "%(receiver)s accepts *%(var_args)s but django signals don't support such arguments.\n"
                    "Consider changing *%(var_args)s to a named collection." % locals()
                )
            rule.arg_rules[receiver] = arg_keys, bool(arg_spec.keywords)

    def _send_to_receiver(rule, receiver, sent_kwargs):
        arg_keys, use_kwargs = rule.arg_rules[receiver]
        if use_kwargs:
            kwargs = sent_kwargs
        else:
            kwargs = {}
            for arg_key in arg_keys[1:]:
                try:
                    kwargs[arg_key] = sent_kwargs.pop(arg_key)
                except KeyError:
                    # unsupplied arguments are ok, there might be defaults.
                    pass
        if arg_keys:
            first_arg = sent_kwargs.pop(arg_keys[0])
            receiver(first_arg, **kwargs)
        else:
            receiver(**kwargs)

    def _send_to_receivers(rule, sender, signal, _kwargs, **unknown_kwargs):
        assert not unknown_kwargs, unknown_kwargs
        # reasons for putting all receivers inside one call
        # - receiver methods don't have to accept kwargs any more, so can use existing methods.
        # - arguments sender and signal can be ignored by receivers
        for receiver in rule.receivers:
            rule._send_to_receiver(receiver, dict(_kwargs))

    def start(rule):
        rule.signal.connect(
            rule._send_to_receivers,
            sender=rule.SendingClass,
            weak=False, # local method
            dispatch_uid=rule.id
        )
    __enter__ = start

    def stop(rule):
        rule.signal.disconnect(
            rule._send_to_receivers,
            sender=rule.SendingClass,
            weak=False,
            dispatch_uid=rule.id
        )
    __exit__ = stop

    def __del__(rule):
        rule.stop()

#    def __call__(rule, function):
#        def wrapped_function_call(*args, **kwargs):
#            with rule:
#                return function(*args, **kwargs)
#        return wrapped_function_call


def when(cause, rule_id=None):
    """Used for configuring handling of business rules in a readable way.

    Sole argument is a SignalMethod.
    This returns a callable that accepts functions that should be run with the passed arguments.
    Thus, note the two sets of parenthesis.

    Arguments passed will be matched to arguments in the receivers by name.

    Signal 'sender' argument will be the class from
    which the signal method was accessed.

    Supplying rule_id is recommended. It is used as the dispatch_uid.

    rule = when(Class.signal)(function,...) returns a SignalHandlingRule.

    rule.stop() will stop the rule.
    """
    def accept_effects(*effects):
        rule = SignalHandlingRule(cause, effects, rule_id)
        rule.start()
        return rule
    return accept_effects

