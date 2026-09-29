import random
R=100_000
viol=0
checks=0
for _ in range(R):
    jk=True; app=False; reserved=False; advertising=True; ps=False
    for step in range(200):
        ev=random.randrange(9)
        if ev==0 and advertising and not app:
            # app connect may race; consumes spare slot
            app=True; advertising=False
        elif ev==1 and app:
            app=False
            if not reserved: advertising=True
        elif ev==2 and jk:
            jk=False
        elif ev==3 and not jk and not reserved:
            jk=True
        elif ev==4 and not ps:
            # reserve: only with JK and no app; stop advertising then recheck
            if jk and not app and not reserved:
                reserved=True; advertising=False
                # model an in-flight app completion after stopAdvertising
                if random.random()<0.01: app=True
                if app or not jk:
                    reserved=False
                    if not app: advertising=True
                else: ps=True
        elif ev==5 and ps:
            ps=False; reserved=False
            if not app: advertising=True
        elif ev==6 and ps and random.random()<0.2:
            # core JK loss aborts PS on next health check
            jk=False; ps=False; reserved=False
            if not app: advertising=True
        # invariants
        checks += 4
        if ps and not reserved: viol+=1
        if ps and app: viol+=1  # race should be caught before PS begins
        if reserved and advertising: viol+=1
        # active conn count cannot exceed configured 2: JK + app + PS
        if int(jk)+int(app)+int(ps)>2: viol+=1
print({'runs':R,'checks':checks,'violations':viol})
