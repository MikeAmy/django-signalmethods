django-signalmethods
====================

This package enhances signal handling in 2 ways:

1. Allows signals to be used as methods.
2. provides a when() decorator

SignalMethods are extensions of django.dispatch.Signal that are python descriptors 
such that they can be used just like other methods.

That is, after they have been defined, they can be called like a method to send the signal.

They are also a bit more flexible:
- arguments sent as non-keyword arguments are mapped to the correct names.

With the when() decorator, they become even more powerful:
- receiver methods don't have to accept kwargs any more, so you can use more of your existing methods.
- arguments sender and signal can be ignored by receivers.


Example:
--------

Simple asteroids game example follows, consider two classes:

    class Spaceship(object):
        def __init__(spaceship):
            spaceship.lives = 3
   
        has_collided = SignalMethod(('spaceship', 'asteroid'))
   
        def explode(spaceship):
            print 'Boom!'
   
        def lose_life(spaceship):
            spaceship.lives -= 1
            if spaceship.lives == 0:
                print 'Game Over'

    class Asteroid(object):
        def destroy(asteroid):
            assert isinstance(asteroid, Asteroid)
            print 'asteroid destroyed'

    asteroid = Asteroid()
    spaceship = Spaceship()

Now:

    Spaceship.has_collided.send(sender=Spaceship, spaceship=spaceship, asteroid=asteroid)

can be written as:

    spaceship.has_collided(asteroid=asteroid)

can even:

    spaceship.has_collided(asteroid)

With the when() decorator, we can configure our signal handling in a very readable way:

    when(Spaceship.has_collided)(Spaceship.explode)

    responses = spaceship.has_collided(asteroid=asteroid)

Output: Boom!


Multiple receivers:
-------------------

    when(Spaceship.has_collided)(
        Spaceship.explode,
        spaceship.lose_life, # calling bound methods is OK
        Asteroid.destroy
    )

    responses = spaceship.has_collided(asteroid=asteroid)

Output: Boom!

asteroid destroyed


More complex rules can be handled as a decorated function:

    @when(Spaceship.has_collided)
    def destroy_spaceship_and_asteroid(spaceship, asteroid, make_noise=True):
        asteroid.destroy()
        if not hasattr(spaceship, 'forcefield'):
            spaceship.explode()
            spaceship.lose_life()

    responses = spaceship.has_collided(asteroid=Asteroid())
    
asteroid destroyed

Output: Boom!

Note that non-keyword arguments will be mapped to the correct name,
and that unneeded arguments are just ignored, and that no arguments
are required (as they may have defaults, like make_noise.

    responses = spaceship.has_collided(Asteroid(), aliens=False)

asteroid destroyed

Output: Boom!

Game Over

Also note that if needed arguments are missing, the usual errors come through:

    responses = spaceship.has_collided()

Output: 

Traceback (most recent call last):

TypeError: destroy_spaceship_and_asteroid() takes at least 2 arguments (1 given)
