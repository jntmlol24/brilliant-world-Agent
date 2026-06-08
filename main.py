T=int(input())
for _ in range(T):
    n,hpa,hpb=map(int,input().split())
    a=list(map(int,input().split()))
    b=list(map(int,input().split()))

    a0=[x for x in a if x!=-1]
    c=a.count(-1)
    b0=[x for x in b if x!=-1]
    s=b.count(-1)

    a0.sort(reverse=True)
    b0.sort()

    a1=a0[:-s] if s > 0 else a0[:]
    b1=b0[:-c] if c > 0 else b0[:]


    i=0
    while i<len(a1) and i<len(b1):
        hpa-=b1[i]
        hpb-=a1[i]
        if hpa<=0 or hpb<=0:
            break
        i+=1

    while i<len(a1) and hpa>0 and  hpb>0:
        hpb-=a1[i]
        i+=1
    while i<len(b1) and hpa>0 and  hpb>0:
        hpa-=b1[i]
        i+=1


    if hpa>0 and hpb<=0:
        print("yes")
    else:
        print("no")